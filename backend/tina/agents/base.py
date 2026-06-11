import sys
import os
import re
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import anthropic
from config import ANTHROPIC_API_KEY, MODEL, SUPABASE_URL, VAULT_DIR, PROJECTS


async def _load_project_context(task: str) -> str:
    """
    Auto-inject project context for any project mentioned in the task.
    Pulls three sources in order: CLAUDE.md, codebase index, recent vault notes.
    """
    task_lower = task.lower()
    for name in PROJECTS:
        if name.lower() not in task_lower:
            continue

        parts        = []
        project_vault = os.path.join(VAULT_DIR, "01-Projects", name)

        # 1. Project CLAUDE.md — architecture, decisions, current state
        claude_md = os.path.join(project_vault, "CLAUDE.md")
        if os.path.exists(claude_md):
            try:
                content = open(claude_md, encoding="utf-8").read()
                if len(content) > 4000:
                    content = content[:4000] + "\n...(truncated — full doc in vault)"
                parts.append(f"[{name.upper()} PROJECT CONTEXT — CLAUDE.md]\n{content}")
            except Exception:
                pass

        # 2. Codebase index — file tree, file descriptions, patterns
        index_path = os.path.join(project_vault, "codebase-index.md")
        if os.path.exists(index_path):
            try:
                content = open(index_path, encoding="utf-8").read()
                if len(content) > 6000:
                    content = content[:6000] + "\n...(truncated — full index in vault)"
                parts.append(f"[{name.upper()} CODEBASE INDEX]\n{content}")
            except Exception:
                pass

        # 3. Recent project notes — decisions, discoveries, technical context
        notes_dir = os.path.join(project_vault, "Notes")
        if os.path.isdir(notes_dir):
            try:
                note_files = sorted(
                    [f for f in os.listdir(notes_dir) if f.endswith(".md")],
                    key=lambda f: os.path.getmtime(os.path.join(notes_dir, f)),
                    reverse=True,
                )[:5]
                if note_files:
                    snippets = []
                    for fname in note_files:
                        content = open(os.path.join(notes_dir, fname), encoding="utf-8").read()
                        snippets.append(f"### {fname}\n{content[:600]}")
                    parts.append(f"[{name.upper()} RECENT VAULT NOTES]\n" + "\n\n".join(snippets))
            except Exception:
                pass

        if parts:
            return "\n\n---\n\n".join(parts)

    return ""

_QUESTION_RE = re.compile(r'\[QUESTION:\s*(.+?)\]', re.DOTALL | re.IGNORECASE)


def _build_tool_content(result) -> str | list:
    """
    Convert a tool result to the correct Anthropic API content format.
    Most tools return a plain string. Screenshot tool returns a dict with
    __type='image' which gets converted to a multimodal content block.
    """
    if not isinstance(result, dict) or result.get("__type") != "image":
        return str(result) if not isinstance(result, str) else result

    return [
        {"type": "text", "text": result.get("text", "Screenshot captured")},
        {
            "type":   "image",
            "source": {
                "type":       "base64",
                "media_type": result.get("media_type", "image/png"),
                "data":       result["data"],
            },
        },
    ]


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

        # Inject codebase index for any project mentioned in the task
        project_ctx = await _load_project_context(task)
        if project_ctx:
            enriched_task = f"{project_ctx}\n\n---\n\n{enriched_task}"

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
                        "content":     _build_tool_content(result),
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
