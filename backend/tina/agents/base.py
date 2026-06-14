import sys
import os
import re
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import anthropic
from config import ANTHROPIC_API_KEY, MODEL, OPUS_MODEL, SUPABASE_URL, VAULT_DIR, PROJECTS

# ── Context management constants ──────────────────────────────────────────────
_TOOL_OUTPUT_MAX_CHARS  = 4_000  # cap any single tool result stored in history
_COMPACT_EVERY_N_CALLS  = 20     # retroactively compress older results every N tool calls
_MAX_TOOL_CALLS         = 80     # inject a wrap-up message after this many tool calls


def _truncate_result(s: str, max_chars: int = _TOOL_OUTPUT_MAX_CHARS) -> str:
    """Truncate a large tool output string before storing in history."""
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n…[truncated — {len(s):,} chars total]"


def _compact_old_tool_results(history: list, keep_tail: int = 10, max_chars: int = 600) -> list:
    """
    Retroactively shrink tool result content in older history entries.
    Keeps the last `keep_tail` messages untouched (recent context stays sharp).
    This prevents context drift on long tasks without breaking the message structure.
    """
    cutoff = max(0, len(history) - keep_tail)
    result = []
    for i, msg in enumerate(history):
        if i >= cutoff or msg.get("role") != "user" or not isinstance(msg.get("content"), list):
            result.append(msg)
            continue
        new_blocks = []
        for block in msg["content"]:
            if (isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and isinstance(block.get("content"), str)
                    and len(block["content"]) > max_chars):
                block = {**block, "content": block["content"][:max_chars] + " …[compressed]"}
            new_blocks.append(block)
        result.append({**msg, "content": new_blocks})
    return result


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


_MAX_DELEGATION_DEPTH = 2  # max chain length: Tina → Agent A → Agent B (no further)


class BaseAgent:
    """
    Specialist agent base class. Each subclass defines:
      - name:             display name broadcast to the dashboard
      - description:      one-line summary used in the request_agent tool for other agents
      - system:           system prompt
      - tool_modules:     list of tool modules (each with DEFINITIONS + handle)
      - allow_delegation: if True, adds a request_agent tool so this agent can
                          sub-delegate to other specialist agents. New agents default
                          to True — set False for sensitive agents (e.g. email).
    """
    name:             str  = "agent"
    description:      str  = ""   # shown to peer agents deciding who to call
    system:           str  = ""
    tool_modules:     list = []
    allow_delegation: bool = True  # opt-out for sensitive agents; new agents get it free
    slack_token:      str  = ""   # bot token for posting to #agents as this agent
    slack_user_id:    str  = ""   # Slack user ID for @mentions by other agents

    def __init__(self):
        self.client    = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self._depth    = 0  # delegation depth — set by _run_sub_agent before spawning
        self._definitions = [d for m in self.tool_modules for d in m.DEFINITIONS]
        self._handlers    = {d["name"]: m.handle for m in self.tool_modules for d in m.DEFINITIONS}

        if self.allow_delegation:
            self._definitions.append(self._build_request_agent_tool())

        group_tool = self._build_group_chat_tool()
        if group_tool:
            self._definitions.append(group_tool)

    def _build_request_agent_tool(self) -> dict:
        from tina.agent import _AGENTS
        # Build a per-agent description so the calling agent knows who does what.
        # Any new agent added to _AGENTS with a `description` field is auto-listed here.
        agent_lines = []
        others = []
        for key, cls in _AGENTS.items():
            if isinstance(self, cls):
                continue
            others.append(key)
            desc = getattr(cls, "description", "") or key
            agent_lines.append(f"  • {key} ({cls.name}): {desc}")
        agent_summary = "\n".join(agent_lines)
        return {
            "name": "request_agent",
            "description": (
                "Delegate a sub-task to another specialist agent and get the result back.\n\n"
                f"Available agents:\n{agent_summary}\n\n"
                "Write a self-contained task brief — the sub-agent has no memory of your "
                "current task. Include all relevant context, file paths, and expected output."
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

    def _build_group_chat_tool(self) -> dict | None:
        """Build a post_to_group tool so this agent can @mention peers in #agents."""
        from tina.agent import _AGENTS
        from config import SLACK_CHANNEL_AGENTS
        if not SLACK_CHANNEL_AGENTS or not self.slack_token:
            return None
        # Build @mention reference for each peer
        peer_lines = []
        for key, cls in _AGENTS.items():
            if isinstance(self, cls):
                continue
            uid  = getattr(cls, "slack_user_id", "")
            mention = f"<@{uid}>" if uid else f"@{cls.name}"
            peer_lines.append(f"  • {key} → {mention} ({cls.name})")
        if not peer_lines:
            return None
        return {
            "name": "post_to_group",
            "description": (
                "Post a message to the #agents group chat as yourself. "
                "Use this to share findings, ask a peer a quick question, or @mention another agent. "
                "The message appears in Slack from your identity.\n\n"
                "To @mention a peer, include their Slack handle in your message:\n"
                + "\n".join(peer_lines)
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to post. Include @mention if addressing a specific agent."},
                },
                "required": ["message"],
            },
        }

    def _post_to_group(self, message: str) -> str:
        """Sync handler: post a message to #agents as this agent."""
        from config import SLACK_CHANNEL_AGENTS
        try:
            from slack_sdk import WebClient
            client = WebClient(token=self.slack_token)
            client.chat_postMessage(channel=SLACK_CHANNEL_AGENTS, text=message)
            return f"Posted to {SLACK_CHANNEL_AGENTS}."
        except Exception as e:
            return f"Failed to post to group: {e}"

    async def _save_task(self, session_id: str, task: str, result: str):
        if not SUPABASE_URL:
            return
        from tina.memory_db import save_turn
        await save_turn(self.name.lower(), session_id, "user",      task)
        await save_turn(self.name.lower(), session_id, "assistant", result)

    async def run(self, task: str, on_tool=None, on_tool_result=None, question_handler=None, plan_handler=None) -> str:
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
        history        = [{"role": "user", "content": enriched_task}]
        qa_rounds      = 0
        tool_call_count = 0

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

                    if block.name == "post_to_group":
                        result = await asyncio.to_thread(
                            self._post_to_group, block.input.get("message", "")
                        )
                    elif block.name == "request_agent" and self.allow_delegation:
                        result = await self._run_sub_agent(
                            block.input.get("agent", ""),
                            block.input.get("task", ""),
                            on_tool=on_tool,
                        )
                    else:
                        handler = self._handlers.get(block.name)
                        try:
                            result = (
                                await asyncio.to_thread(handler, block.name, block.input)
                                if handler else f"Unknown tool: {block.name}"
                            )
                            if on_tool_result:
                                await on_tool_result(block.name, block.input, result)
                        except Exception as exc:
                            result = (
                                f"Tool '{block.name}' raised an error: {exc}. "
                                "Try a different approach or skip this step."
                            )
                            print(f"[{self.name}] tool error ({block.name}): {exc}")

                    # Truncate large outputs before storing — reduces context bloat
                    stored = _truncate_result(result) if isinstance(result, str) else result
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     _build_tool_content(stored),
                    })

                tool_call_count += len([b for b in response.content if b.type == "tool_use"])
                history.append({"role": "user", "content": tool_results})

                # Retroactively compress older tool results every N calls
                if tool_call_count % _COMPACT_EVERY_N_CALLS == 0 and tool_call_count > 0:
                    history = _compact_old_tool_results(history)
                    print(f"[{self.name}] context compacted at {tool_call_count} tool calls")

                # Safety ceiling — force a final response rather than looping forever
                if tool_call_count >= _MAX_TOOL_CALLS:
                    print(f"[{self.name}] reached {_MAX_TOOL_CALLS} tool call limit — forcing wrap-up")
                    history.append({
                        "role": "user",
                        "content": (
                            f"You have made {tool_call_count} tool calls. "
                            "Stop all tool calls now. Write your complete final response — "
                            "summarise what you accomplished, what code or files were produced, "
                            "and what (if anything) remains. No more tool calls after this."
                        ),
                    })

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
        if self._depth >= _MAX_DELEGATION_DEPTH:
            return (
                f"Delegation depth limit ({_MAX_DELEGATION_DEPTH}) reached — "
                "cannot sub-delegate further. Complete the task with your own tools."
            )
        cls = _AGENTS.get(agent_key)
        if not cls:
            return f"Unknown agent: {agent_key}"
        if isinstance(self, cls):
            return "Cannot delegate to self."
        print(f"[{self.name}] (depth {self._depth}) delegating to {agent_key}: {task[:60]}...")
        specialist = cls()
        specialist._depth = self._depth + 1
        return await specialist.run(task, on_tool=on_tool)
