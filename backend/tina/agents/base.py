import sys
import os
import re
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import anthropic
from config import ANTHROPIC_API_KEY, MODEL, OPUS_MODEL, SUPABASE_URL, VAULT_DIR, PROJECTS


_COMPLEX_KEYWORDS = {
    "architect", "refactor", "redesign", "integrate", "migration", "migrate",
    "rebuild", "rewrite", "multiple files", "across", "system", "overhaul",
    "phase", "pipeline", "infrastructure", "database", "schema", "deploy",
}


def _is_complex_task(task: str) -> bool:
    """Heuristic: use Opus when the task is architecturally significant."""
    task_lower = task.lower()
    keyword_hit = any(kw in task_lower for kw in _COMPLEX_KEYWORDS)
    long_brief  = len(task) > 500
    return keyword_hit or long_brief


def _semantic_vault_notes(task: str, search_dirs: list[str], max_notes: int = 6, chars_each: int = 700) -> str:
    """
    Find vault notes most relevant to this task using keyword overlap scoring.
    Searches across Notes/, Decisions/, and Learned/ for the project.
    """
    task_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', task.lower()))
    if not task_words:
        return ""

    scored: list[tuple[int, str, str]] = []
    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for fname in os.listdir(directory):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(directory, fname)
            try:
                content = open(fpath, encoding="utf-8", errors="replace").read()
                note_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', content.lower()))
                score = len(task_words & note_words)
                if score >= 3:
                    scored.append((score, fname, content))
            except Exception:
                continue

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    snippets = [
        f"### {fname} (relevance: {score})\n{content[:chars_each]}"
        for score, fname, content in scored[:max_notes]
    ]
    return "\n\n".join(snippets)


async def _load_project_context(task: str) -> str:
    """
    Auto-inject project context for any project mentioned in the task.
    Sources: CLAUDE.md, codebase index, semantically relevant vault notes.
    """
    task_lower = task.lower()
    for name in PROJECTS:
        if name.lower() not in task_lower:
            continue

        parts         = []
        project_vault = os.path.join(VAULT_DIR, "01-Projects", name)

        # 1. Project CLAUDE.md — architecture, decisions, current state
        claude_md = os.path.join(project_vault, "CLAUDE.md")
        if os.path.exists(claude_md):
            try:
                content = open(claude_md, encoding="utf-8").read()
                if len(content) > 5000:
                    content = content[:5000] + "\n...(truncated)"
                parts.append(f"[{name.upper()} PROJECT CONTEXT — CLAUDE.md]\n{content}")
            except Exception:
                pass

        # 2. Codebase index — file tree, file descriptions, patterns
        index_path = os.path.join(project_vault, "codebase-index.md")
        if os.path.exists(index_path):
            try:
                content = open(index_path, encoding="utf-8").read()
                if len(content) > 7000:
                    content = content[:7000] + "\n...(truncated)"
                parts.append(f"[{name.upper()} CODEBASE INDEX]\n{content}")
            except Exception:
                pass

        # 3. Semantically relevant vault notes — matched to THIS task's keywords
        search_dirs = [
            os.path.join(project_vault,        "Notes"),
            os.path.join(project_vault,        "Decisions"),
            os.path.join(VAULT_DIR, "02-Tina-Memory", "Decisions"),
            os.path.join(VAULT_DIR, "02-Tina-Memory", "Learned"),
        ]
        relevant = _semantic_vault_notes(task, search_dirs)
        if relevant:
            parts.append(f"[{name.upper()} RELEVANT VAULT NOTES]\n{relevant}")

        if parts:
            return "\n\n---\n\n".join(parts)

    return ""

_QUESTION_RE = re.compile(r'\[QUESTION:\s*(.+?)\]', re.DOTALL | re.IGNORECASE)
_PLAN_RE     = re.compile(r'\[PLAN:\s*(.+?)\]',     re.DOTALL | re.IGNORECASE)


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

    async def run(self, task: str, on_tool=None, question_handler=None, plan_handler=None) -> str:
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

        model     = OPUS_MODEL if _is_complex_task(task) else MODEL
        history   = [{"role": "user", "content": enriched_task}]
        qa_rounds = 0

        while True:
            kwargs = dict(
                model=model,
                max_tokens=8192,
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

                # Check for a plan awaiting Ky approval before execution
                if plan_handler:
                    match = _PLAN_RE.search(reply)
                    if match:
                        plan     = match.group(1).strip()
                        feedback = await plan_handler(plan)
                        history.append({"role": "assistant", "content": response.content})
                        if feedback.strip().lower() in ("approved", "yes", "go", "proceed", "ok"):
                            history.append({"role": "user", "content": "Plan approved. Execute it now."})
                        else:
                            history.append({
                                "role":    "user",
                                "content": f"Plan feedback: {feedback}\n\nRevise your approach and proceed.",
                            })
                        continue

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
