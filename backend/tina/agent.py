import sys
import os
import asyncio
import uuid
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import anthropic
from config import ANTHROPIC_API_KEY, SYSTEM_PROMPT, MODEL, ORCHESTRATOR_MODEL, SUPABASE_URL, SLACK_SAM_USER_ID, SLACK_KAI_USER_ID
from tools import weather, vault, calendar_tool, github_tool, slack_tool, docs_tool, project_tool, system_tool
from tina.agents.research import ResearchAgent
from tina.agents.coding   import CodingAgent
from tina.agents.email    import EmailAgent
from tina.agents.data     import DataAgent

# ── Specialist agent registry ─────────────────────────────────────────────────
_AGENTS: dict[str, type] = {
    "research": ResearchAgent,
    "coding":   CodingAgent,
    "email":    EmailAgent,
    "data":     DataAgent,
}

# ── Direct tools (Tina handles herself without delegating) ────────────────────
_DIRECT_MODULES  = [weather, vault, calendar_tool, github_tool, slack_tool, docs_tool, project_tool, system_tool]
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
        "Use 'data' (Morgan) for analysing CSV/Excel/JSON files, financial data, spreadsheets, "
        "statistics, generating charts, or any task involving structured data from local files. "
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

# ── Conversation history search tool ─────────────────────────────────────────
_SEARCH_HISTORY_TOOL = {
    "name":        "search_conversation_history",
    "description": (
        "Search the full conversation history in the database for any topic or keyword — "
        "going back further than the 40-turn context window. "
        "Use this when Ky references something that may have been discussed in a previous session, "
        "or when you want to check whether something has already been covered before answering."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type":        "string",
                "description": "Keyword or phrase to search for across all past conversations.",
            },
        },
        "required": ["query"],
    },
}

# ── Agent status tool ────────────────────────────────────────────────────────
_STATUS_TOOL = {
    "name":        "get_agent_status",
    "description": (
        "Check the current progress of a background agent that is actively working on a task. "
        "Returns what the agent is doing right now, how long they've been running, and their recent tool activity. "
        "Use this when Ky asks what Sam or Research is up to, how far along they are, or whether they're still working."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {
                "type":        "string",
                "enum":        list(_AGENTS.keys()),
                "description": "Which agent to check.",
            },
        },
        "required": ["agent"],
    },
}

_ALL_TOOLS = _DIRECT_DEFS + [_DELEGATE_TOOL, _DIAG_TOOL, _STATUS_TOOL, _SEARCH_HISTORY_TOOL]

# ── Extended thinking heuristic ───────────────────────────────────────────────
_THINKING_KEYWORDS = frozenset([
    "plan", "should", "best", "compare", "advice", "strategy",
    "decide", "explain", "analyse", "analyze", "design", "recommend",
    "options", "trade", "pros", "cons", "help me", "what do you think",
    "how do i", "how should", "which is better", "which one",
    "why", "architecture", "approach", "problem", "issue", "debug",
    "review", "evaluate", "assess", "consider", "think about",
])

def _warrants_thinking(message: str) -> bool:
    """Returns True when the request is complex enough to warrant extended thinking."""
    if len(message) > 200:
        return True
    lower = message.lower()
    return any(kw in lower for kw in _THINKING_KEYWORDS)


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

    async def chat(self, message: str, on_tool=None, on_tool_result=None, on_agent_done=None, background: bool = True) -> str:
        await self._ensure_history_loaded()
        self.history.append({"role": "user", "content": message})

        use_thinking = _warrants_thinking(message)
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

            thinking_kwargs = (
                {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
                if use_thinking else {}
            )
            response = await self.client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=8000 if use_thinking else 1024,
                system=system,
                tools=_ALL_TOOLS,
                messages=self.history,
                **thinking_kwargs,
            )

            if response.stop_reason == "tool_use":
                self.history.append({"role": "assistant", "content": response.content})
                tool_blocks = [b for b in response.content if b.type == "tool_use"]

                # Notify dashboard of all pending calls upfront, then dispatch in parallel
                if on_tool:
                    for block in tool_blocks:
                        await on_tool(block.name, block.input)

                _NO_RESULT_BROADCAST = frozenset(
                    ("delegate_to_agent", "run_diagnostics", "get_agent_status", "search_conversation_history")
                )

                async def _run_one(block):
                    result = await self._dispatch(block.name, block.input, on_tool, on_agent_done, background)
                    if on_tool_result and block.name not in _NO_RESULT_BROADCAST:
                        await on_tool_result(block.name, block.input, result)
                    return {
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    }

                tool_results = list(await asyncio.gather(*[_run_one(b) for b in tool_blocks]))
                self.history.append({"role": "user", "content": tool_results})

            else:
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")
                self.history.append({"role": "assistant", "content": response.content})
                asyncio.create_task(self._save_turns(message, reply))
                return reply

    async def _dispatch(self, name: str, inputs: dict, on_tool=None, on_agent_done=None, background: bool = True) -> str:
        if name == "search_conversation_history":
            if SUPABASE_URL:
                from tina.memory_db import search_history
                return await search_history(inputs.get("query", ""))
            return "Supabase not configured — conversation history unavailable."

        if name == "get_agent_status":
            from tina.agent_state import get_status
            return get_status(inputs.get("agent", ""))

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
