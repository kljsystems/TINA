import sys
import os
import asyncio
import uuid
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import anthropic
from config import ANTHROPIC_API_KEY, SYSTEM_PROMPT, MODEL, ORCHESTRATOR_MODEL, SUPABASE_URL, model_for, effort_for
from tina.llm import RoutedLLM
from tools import weather, vault, calendar_tool, github_tool, slack_tool, docs_tool, project_tool, system_tool, video_tool, capture_tool, kaos_tool, social_tool, gdrive_tool, stripe_tool
from tina.agents.base import _build_tool_content
from tina.agents.research  import ResearchAgent
from tina.agents.coding    import CodingAgent
from tina.agents.email     import EmailAgent
from tina.agents.data      import DataAgent
from tina.agents.marketing import MarketingAgent
from tina.agents.website   import WebsiteAgent
from tina.agents.pm        import ProjectManagerAgent

# ── Specialist agent registry ─────────────────────────────────────────────────
_AGENTS: dict[str, type] = {
    "research":  ResearchAgent,
    "coding":    CodingAgent,
    "email":     EmailAgent,
    "data":      DataAgent,
    "marketing": MarketingAgent,
    "website":   WebsiteAgent,
    "pm":        ProjectManagerAgent,
}

# ── Direct tools (Tina handles herself without delegating) ────────────────────
_DIRECT_MODULES  = [weather, vault, calendar_tool, github_tool, slack_tool, docs_tool, project_tool, system_tool, video_tool, capture_tool, kaos_tool, social_tool, gdrive_tool, stripe_tool]
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
        "Use 'data' (Connor) for analysing CSV/Excel/JSON files, financial data, spreadsheets, "
        "statistics, generating charts, or any task involving structured data from local files. "
        "Use 'marketing' (Wade) for social media content — drafting posts, video scripts, video ideas, "
        "trend research, and posting to Facebook or Instagram. "
        "Use 'website' for anything web — UI/UX design, layouts, colour, typography, HTML/CSS/JS, React, Next.js, "
        "SEO, performance, accessibility, and CMS platforms like WordPress. "
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
            "then_agent": {
                "type":        "string",
                "enum":        list(_AGENTS.keys()),
                "description": "Optional: agent to run automatically when this one finishes. Use for multi-step pipelines (e.g. Charlie researches → Sam builds).",
            },
            "then_task": {
                "type":        "string",
                "description": "Task brief for the follow-on agent. Use {result} to include a summary of the first agent's output.",
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

# ── Promote project tool ──────────────────────────────────────────────────────
_PROMOTE_TOOL = {
    "name":        "promote_project",
    "description": (
        "Promote a proposed project from the inbox pipeline to active status. "
        "Use when Ky says 'promote X', 'approve X', 'let's go with X', 'activate X project', "
        "or any variant of approving a project that was auto-researched by Charlie. "
        "The project must have been through the inbox pipeline (captured → classified → proposed). "
        "After promotion the project is active and ready for execution."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_name": {
                "type":        "string",
                "description": "The project name to promote — partial names and fuzzy matches are fine.",
            },
        },
        "required": ["project_name"],
    },
}

_ALL_TOOLS = _DIRECT_DEFS + [_DELEGATE_TOOL, _DIAG_TOOL, _STATUS_TOOL, _SEARCH_HISTORY_TOOL, _PROMOTE_TOOL]

# ── Extended thinking heuristic ───────────────────────────────────────────────
# Only trigger for genuinely strategic/architectural requests, not casual conversation.
_THINKING_KEYWORDS = frozenset([
    "architect", "redesign", "compare options", "strategy",
    "trade-offs", "pros and cons", "evaluate options",
    "design from scratch", "recommend approach", "assess the best",
    "which approach is better", "how should we design",
])

def _warrants_thinking(message: str) -> bool:
    """Returns True when the request is complex enough to warrant extended thinking."""
    if len(message) > 800:
        return True
    lower = message.lower()
    return any(kw in lower for kw in _THINKING_KEYWORDS)


class TinaAgent:
    def __init__(self, background_runner=None, diag_runner=None):
        self.client            = RoutedLLM(api_key=ANTHROPIC_API_KEY)
        self.history:list[dict] = []
        self.background_runner = background_runner  # injected by main.py
        self.diag_runner       = diag_runner        # injected by main.py
        self.session_id        = str(uuid.uuid4())
        self._history_loaded   = False

    @property
    def has_background_runner(self) -> bool:
        return self.background_runner is not None

    # Assistant turns containing these phrases came from a bug where Tina
    # bypassed Jamie and generated website files herself. They must not be
    # fed back as context or Tina will keep repeating the bad behaviour.
    _HISTORY_POISON = (
        "document generator",
        "generate_document",
        "no agents, no delegation",
        "not using agents",
        "bypassing agent",
        "bypass agent",
        "file write is broken",
        "file-write tool is",
        "straight through my",
        "going directly",
        "not delegating",
    )

    @staticmethod
    def _load_context_brief() -> str:
        """Load the persistent context brief from vault. TINA updates this herself via vault_write."""
        try:
            from config import VAULT_DIR
            path = os.path.join(VAULT_DIR, "02-Tina-Memory", "context-brief.md")
            if os.path.exists(path):
                content = open(path, encoding="utf-8").read().strip()
                return content[:3000]  # cap so it never bloats history
        except Exception as e:
            print(f"[TinaAgent] context brief load error: {e}")
        return ""

    async def _ensure_history_loaded(self):
        if self._history_loaded or not SUPABASE_URL:
            self._history_loaded = True
            return
        self._history_loaded = True
        from tina.memory_db import load_history
        raw = await load_history("tina", limit=20)
        cleaned = []
        for msg in raw:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    text = content.lower()
                elif isinstance(content, list):
                    text = " ".join(
                        (b.get("text", "") if isinstance(b, dict) else getattr(b, "text", ""))
                        for b in content
                    ).lower()
                else:
                    text = ""
                if any(phrase in text for phrase in self._HISTORY_POISON):
                    # Remove the paired user turn too
                    if cleaned and cleaned[-1].get("role") == "user":
                        cleaned.pop()
                    print(f"[TinaAgent] stripped poisoned history turn: {text[:80]!r}")
                    continue
            cleaned.append(msg)

        # Prepend context brief as a synthetic first exchange so TINA always has
        # persistent facts about Ky and KLJ regardless of what's in the recent turns.
        brief = self._load_context_brief()
        if brief:
            self.history = [
                {"role": "user",      "content": f"[MEMORY CONTEXT — read at startup]\n\n{brief}"},
                {"role": "assistant", "content": "Context loaded."},
            ] + cleaned
            print(f"[TinaAgent] context brief injected ({len(brief)} chars)")
        else:
            self.history = cleaned

        if cleaned:
            print(f"[TinaAgent] loaded {len(cleaned)} turns ({len(raw) - len(cleaned)} poisoned turns stripped)")

    async def _save_turns(self, user_msg: str, assistant_reply: str):
        if not SUPABASE_URL:
            return
        from tina.memory_db import save_turn
        await save_turn("tina", self.session_id, "user",      user_msg)
        await save_turn("tina", self.session_id, "assistant", assistant_reply)

    @staticmethod
    def _sanitize_history(history: list) -> list:
        """Remove broken tool_use/tool_result pairs anywhere in history.

        Two cases handled:
        1. Orphaned tool_use — assistant message whose tool_use ids are not fully
           covered by the immediately following user message's tool_result ids.
        2. Orphaned tool_result — user message whose tool_result ids don't all appear
           as tool_use ids in the immediately preceding assistant message.

        Both arise from WS drops that interrupt a tool-call cycle mid-flight, leaving
        dangling blocks that Anthropic rejects with a 400 on the next request.
        """
        def _use_ids(content) -> set:
            ids = set()
            if not isinstance(content, list):
                return ids
            for b in content:
                if (getattr(b, "type", None) == "tool_use" or
                        (isinstance(b, dict) and b.get("type") == "tool_use")):
                    bid = getattr(b, "id", None) or (b.get("id") if isinstance(b, dict) else None)
                    if bid:
                        ids.add(bid)
            return ids

        def _result_ids(content) -> set:
            ids = set()
            if not isinstance(content, list):
                return ids
            for b in content:
                if (getattr(b, "type", None) == "tool_result" or
                        (isinstance(b, dict) and b.get("type") == "tool_result")):
                    bid = (getattr(b, "tool_use_id", None) or
                           (b.get("tool_use_id") if isinstance(b, dict) else None))
                    if bid:
                        ids.add(bid)
            return ids

        result = []
        i = 0
        while i < len(history):
            msg = history[i]

            if msg.get("role") == "assistant":
                use_ids = _use_ids(msg.get("content", []))
                if use_ids:
                    next_msg = history[i + 1] if i + 1 < len(history) else None
                    next_res_ids = _result_ids(next_msg.get("content", []) if next_msg else [])
                    if not use_ids.issubset(next_res_ids):
                        # Drop this assistant turn; if the next message is a partial
                        # tool_result user turn, drop that too.
                        skip = 2 if (next_msg and next_res_ids and
                                     next_msg.get("role") == "user") else 1
                        i += skip
                        continue

            elif msg.get("role") == "user":
                res_ids = _result_ids(msg.get("content", []))
                if res_ids:
                    prev = result[-1] if result else None
                    prev_use_ids = _use_ids(prev.get("content", []) if prev else [])
                    if not res_ids.issubset(prev_use_ids):
                        # Orphaned tool_result — also remove the preceding assistant
                        # message that was just appended (it has no complete pair now).
                        if result and result[-1].get("role") == "assistant":
                            result.pop()
                        i += 1
                        continue

            result.append(msg)
            i += 1
        return result

    async def chat(self, message: str, on_tool=None, on_tool_result=None, on_agent_done=None, background: bool = True) -> str:
        await self._ensure_history_loaded()
        self.history = self._sanitize_history(self.history)
        self.history.append({"role": "user", "content": message})

        use_thinking = _warrants_thinking(message)

        # Pre-build cached system + tools (stable across turns — cache saves ~90% on re-sends)
        now = datetime.now()
        _system_text = (
            f"Current date: {now.strftime('%A, %d %B %Y')}\n"
            f"Current time: {now.strftime('%I:%M %p')} (Sydney)\n\n"
        ) + SYSTEM_PROMPT
        _system_cached = [{"type": "text", "text": _system_text, "cache_control": {"type": "ephemeral"}}]
        _tools_cached  = [*_ALL_TOOLS[:-1], {**_ALL_TOOLS[-1], "cache_control": {"type": "ephemeral"}}]

        while True:
            _orch_model = model_for("tina")
            # On hard turns, give Tina adaptive thinking + high reasoning effort for
            # sharper routing. Orchestrator uses auto tool_choice, so thinking is safe
            # here (forced tool_choice would conflict). Adaptive replaces the removed
            # budget_tokens form. The local adapter drops both kwargs.
            thinking_kwargs = {}
            if use_thinking:
                thinking_kwargs["thinking"] = {"type": "adaptive"}
                _eff = effort_for(_orch_model, complex=True)
                if _eff:
                    thinking_kwargs["output_config"] = {"effort": _eff}
            response = await self.client.messages.create(
                model=_orch_model,
                max_tokens=6000 if use_thinking else 1024,
                system=_system_cached,
                tools=_tools_cached,
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
                    ("delegate_to_agent", "run_diagnostics", "get_agent_status",
                     "search_conversation_history", "video_download", "video_process")
                )

                async def _run_one(block):
                    result = await self._dispatch(block.name, block.input, on_tool, on_agent_done, background)
                    if on_tool_result and block.name not in _NO_RESULT_BROADCAST:
                        await on_tool_result(block.name, block.input, result)
                    content = _build_tool_content(result)
                    return {
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     content,
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

            then_spec = None
            if inputs.get("then_agent"):
                then_cls = _AGENTS.get(inputs["then_agent"])
                if then_cls:
                    then_spec = {
                        "agent": inputs["then_agent"],
                        "cls":   then_cls,
                        "task":  inputs.get("then_task", ""),
                    }

            if self.background_runner and background:
                # Non-blocking: agent runs independently, Tina continues immediately
                await self.background_runner(agent_key, cls, task, on_tool, then_spec=then_spec)
                handoff_note = (
                    f" {inputs['then_agent'].capitalize()} will automatically start when {agent_key} finishes."
                    if then_spec else ""
                )
                return (
                    f"Background task dispatched to {agent_key}.{handoff_note} "
                    "Ky will be notified via Slack and the dashboard when complete."
                )

            # Blocking fallback (Slack, /api/chat, background=False)
            specialist = cls()
            result     = await specialist.run(task, on_tool=on_tool)
            if on_agent_done:
                await on_agent_done(agent_key)
            return result

        if name == "promote_project":
            project_name = inputs.get("project_name", "")
            try:
                import sys as _sys
                import os as _os
                _backend_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                _tina_root    = _os.path.dirname(_backend_root)
                if _tina_root not in _sys.path:
                    _sys.path.insert(0, _tina_root)
                if _backend_root not in _sys.path:
                    _sys.path.insert(0, _backend_root)
                from main import _promote_project
                result = await asyncio.to_thread(_promote_project, project_name)
            except ImportError:
                return "Promote tool not available in this context."

            if "active status" in result and self.background_runner:
                import re as _re
                slug = _re.sub(r"[^\w\s-]", "", project_name.lower())
                slug = _re.sub(r"[\s_]+", "-", slug).strip("-")[:60]
                morgan_task = (
                    f"EXECUTE PROJECT: {project_name}\n\n"
                    f"{result}\n\n"
                    f"The active project folder is 01-Projects/{slug}/ (or the closest match to that name). "
                    "Read capture.md and research.md from that folder, build an execution plan, "
                    "and coordinate the right agents to complete the project."
                )
                await self.background_runner("pm", ProjectManagerAgent, morgan_task, None)

            return result

        handler = _DIRECT_HANDLERS.get(name)
        if handler:
            return await asyncio.to_thread(handler, name, inputs)

        return f"Unknown tool: {name}"

    def reset(self):
        self.history        = []
        self.session_id     = str(uuid.uuid4())
        self._history_loaded = False  # reload from DB on next chat()
