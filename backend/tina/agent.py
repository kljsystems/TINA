import sys
import os
import asyncio
import uuid
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import anthropic
from config import ANTHROPIC_API_KEY, SYSTEM_PROMPT, MODEL, ORCHESTRATOR_MODEL, SUPABASE_URL, SLACK_SAM_USER_ID, SLACK_KAI_USER_ID
from tools import weather, vault, calendar_tool, github_tool, slack_tool
from tina.agents.research import ResearchAgent
from tina.agents.coding   import CodingAgent

# ── Specialist agent registry ─────────────────────────────────────────────────
_AGENTS: dict[str, type] = {
    "research": ResearchAgent,
    "coding":   CodingAgent,
}

# ── Direct tools (Tina handles herself without delegating) ────────────────────
_DIRECT_MODULES  = [weather, vault, calendar_tool, github_tool, slack_tool]
_DIRECT_DEFS     = [d for m in _DIRECT_MODULES for d in m.DEFINITIONS]
_DIRECT_HANDLERS = {d["name"]: m.handle for m in _DIRECT_MODULES for d in m.DEFINITIONS}

# ── Diagnostics tool ─────────────────────────────────────────────────────────
_DIAG_TOOL = {
    "name":        "run_diagnostics",
    "description": (
        "Run a full system diagnostic. Tests all API keys, services, agents, "
        "memory, and integrations. Results stream live to the dashboard. "
        "Use when Ky asks you to run a diagnostic, check system health, "
        "or verify that everything is working."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

# ── Delegation tool ───────────────────────────────────────────────────────────
_DELEGATE_TOOL = {
    "name":        "delegate_to_agent",
    "description": (
        "Delegate a task to a specialist agent. "
        "In WebSocket mode the agent runs as an independent background task — Kai is notified via Slack and the dashboard when done. "
        "Use 'research' for web searches, news, Wikipedia lookups, or any fact-finding. "
        "Use 'coding' (Sam) for ANYTHING code-related: writing code, debugging, code review, "
        "architecture decisions, explaining how code works, fixing bugs, choosing a library, "
        "setting up a project, technical how-to questions, or anything involving a programming language. "
        "When in doubt about whether something is code-related, send it to Sam. "
        "Write a clear task brief — include all relevant context, repo names, file paths, and what outcome is needed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {
                "type":        "string",
                "enum":        list(_AGENTS.keys()),
                "description": "Which specialist to delegate to.",
            },
            "task": {
                "type":        "string",
                "description": "Full task brief for the specialist, including relevant context.",
            },
        },
        "required": ["agent", "task"],
    },
}

_ALL_TOOLS = _DIRECT_DEFS + [_DELEGATE_TOOL, _DIAG_TOOL]


class TinaAgent:
    def __init__(self, background_runner=None, diag_runner=None):
        self.client            = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.history:list[dict] = []
        self.background_runner = background_runner  # injected by main.py
        self.diag_runner       = diag_runner        # injected by main.py
        self.session_id        = str(uuid.uuid4())
        self._history_loaded   = False

    @property
    def has_background_runner(self) -> bool:
        return self.background_runner is not None

    async def _ensure_history_loaded(self):
        if self._history_loaded or not SUPABASE_URL:
            self._history_loaded = True
            return
        self._history_loaded = True
        from tina.memory_db import load_history
        self.history = await load_history("tina", limit=40)
        if self.history:
            print(f"[TinaAgent] loaded {len(self.history)} turns from memory")

    async def _save_turns(self, user_msg: str, assistant_reply: str):
        if not SUPABASE_URL:
            return
        from tina.memory_db import save_turn
        await save_turn("tina", self.session_id, "user",      user_msg)
        await save_turn("tina", self.session_id, "assistant", assistant_reply)

    async def chat(self, message: str, on_tool=None, on_agent_done=None, background: bool = True) -> str:
        await self._ensure_history_loaded()
        self.history.append({"role": "user", "content": message})

        while True:
            now = datetime.now()
            system = (
                f"Current date: {now.strftime('%A, %d %B %Y')}\n"
                f"Current time: {now.strftime('%I:%M %p')} (Sydney)\n\n"
            ) + SYSTEM_PROMPT.replace(
                "{SLACK_SAM_USER_ID}", SLACK_SAM_USER_ID or "Sam"
            ).replace(
                "{SLACK_KAI_USER_ID}", SLACK_KAI_USER_ID or "Ky"
            )

            response = await self.client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=1024,
                system=system,
                tools=_ALL_TOOLS,
                messages=self.history,
            )

            if response.stop_reason == "tool_use":
                self.history.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if on_tool:
                        await on_tool(block.name, block.input)
                    result = await self._dispatch(block.name, block.input, on_tool, on_agent_done, background)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

                self.history.append({"role": "user", "content": tool_results})

            else:
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")
                self.history.append({"role": "assistant", "content": response.content})
                asyncio.create_task(self._save_turns(message, reply))
                return reply

    async def _dispatch(self, name: str, inputs: dict, on_tool=None, on_agent_done=None, background: bool = True) -> str:
        if name == "run_diagnostics":
            if self.diag_runner:
                await self.diag_runner()
            return "Diagnostics running — results are streaming live to the dashboard."

        if name == "delegate_to_agent":
            agent_key = inputs.get("agent", "")
            task      = inputs.get("task", "")
            cls       = _AGENTS.get(agent_key)
            if not cls:
                return f"Unknown agent: {agent_key}"

            if self.background_runner and background:
                # Non-blocking: agent runs independently, Tina continues immediately
                await self.background_runner(agent_key, cls, task, on_tool)
                return (
                    f"Background task dispatched to {agent_key}. "
                    "Kai will be notified via Slack and the dashboard when complete."
                )

            # Blocking fallback (Slack, /api/chat, background=False)
            specialist = cls()
            result     = await specialist.run(task, on_tool=on_tool)
            if on_agent_done:
                await on_agent_done(agent_key)
            return result

        handler = _DIRECT_HANDLERS.get(name)
        if handler:
            return await asyncio.to_thread(handler, name, inputs)

        return f"Unknown tool: {name}"

    def reset(self):
        self.history        = []
        self.session_id     = str(uuid.uuid4())
        self._history_loaded = False  # reload from DB on next chat()
