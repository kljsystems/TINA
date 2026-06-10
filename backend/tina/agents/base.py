import sys
import os
import re
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import anthropic
from config import ANTHROPIC_API_KEY, MODEL, SUPABASE_URL

_QUESTION_RE = re.compile(r'\[QUESTION:\s*(.+?)\]', re.DOTALL | re.IGNORECASE)


class BaseAgent:
    """
    Specialist agent base class. Each subclass defines:
      - name:             display name broadcast to the dashboard
      - system:           system prompt
      - tool_modules:     list of tool modules (each with DEFINITIONS + handle)
      - allow_delegation: if True, adds a request_agent tool so this agent can
                          call other specialist agents as sub-tasks
    """
    name:             str  = "agent"
    system:           str  = ""
    tool_modules:     list = []
    allow_delegation: bool = False

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self._definitions = [d for m in self.tool_modules for d in m.DEFINITIONS]
        self._handlers    = {d["name"]: m.handle for m in self.tool_modules for d in m.DEFINITIONS}

        if self.allow_delegation:
            self._definitions.append(self._build_request_agent_tool())

    def _build_request_agent_tool(self) -> dict:
        from tina.agent import _AGENTS
        others = [k for k, v in _AGENTS.items() if not isinstance(self, v)]
        return {
            "name": "request_agent",
            "description": (
                "Ask another specialist agent to complete a sub-task and return the result. "
                "Use 'research' to look things up, search the web, find documentation, or "
                "gather any information you need. Write a clear, complete task brief."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": others, "description": "Which agent to call."},
                    "task":  {"type": "string", "description": "Full task brief for the sub-agent."},
                },
                "required": ["agent", "task"],
            },
        }

    async def _save_task(self, session_id: str, task: str, result: str):
        if not SUPABASE_URL:
            return
        from tina.memory_db import save_turn
        await save_turn(self.name.lower(), session_id, "user",      task)
        await save_turn(self.name.lower(), session_id, "assistant", result)

    async def run(self, task: str, on_tool=None, question_handler=None) -> str:
        """
        Run the agent on a task and return the result as a string.
        If question_handler is provided and the agent writes [QUESTION: ...],
        the handler is called and the answer is fed back before continuing.
        """
        import asyncio
        session_id = str(uuid.uuid4())

        # Inject recent work context so the agent remembers past tasks
        enriched_task = task
        if SUPABASE_URL:
            from tina.memory_db import load_recent_tasks
            recent = await load_recent_tasks(self.name.lower(), limit=8)
            if recent:
                enriched_task = f"{recent}\n\n---\n\nCURRENT TASK:\n\n{task}"

        history   = [{"role": "user", "content": enriched_task}]
        qa_rounds = 0

        while True:
            kwargs = dict(
                model=MODEL,
                max_tokens=4096,
                system=self.system,
                messages=history,
            )
            if self._definitions:
                kwargs["tools"] = self._definitions

            response = await self.client.messages.create(**kwargs)

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if on_tool:
                        await on_tool(block.name, block.input)

                    if block.name == "request_agent" and self.allow_delegation:
                        result = await self._run_sub_agent(
                            block.input.get("agent", ""),
                            block.input.get("task", ""),
                            on_tool=on_tool,
                        )
                    else:
                        handler = self._handlers.get(block.name)
                        result  = (
                            await asyncio.to_thread(handler, block.name, block.input)
                            if handler else f"Unknown tool: {block.name}"
                        )
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
                history.append({"role": "user", "content": tool_results})

            else:
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")

                # Check if agent is asking a clarifying question
                if question_handler and qa_rounds < 5:
                    match = _QUESTION_RE.search(reply)
                    if match:
                        question = match.group(1).strip()
                        qa_rounds += 1
                        answer = await question_handler(question)
                        history.append({"role": "assistant", "content": response.content})
                        history.append({
                            "role":    "user",
                            "content": f"Tina's answer: {answer}\n\nContinue with the task.",
                        })
                        continue

                asyncio.create_task(self._save_task(session_id, task, reply))
                return reply

    async def _run_sub_agent(self, agent_key: str, task: str, on_tool=None) -> str:
        """Run another specialist agent as a synchronous sub-task."""
        from tina.agent import _AGENTS
        cls = _AGENTS.get(agent_key)
        if not cls:
            return f"Unknown agent: {agent_key}"
        if isinstance(self, cls):
            return "Cannot delegate to self."
        print(f"[{self.name}] delegating to {agent_key}: {task[:60]}...")
        specialist = cls()
        return await specialist.run(task, on_tool=on_tool)
