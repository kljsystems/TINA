import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)                            # TINA root → config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend/ → tina package

# Force UTF-8 on Windows so emojis and non-ASCII characters print correctly
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import base64
import json as _json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import httpx
import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from config import (
    ANTHROPIC_API_KEY, MODEL, ORCHESTRATOR_MODEL, SYSTEM_PROMPT,
    DEEPGRAM_API_KEY, ELEVENLABS_API_KEY,
    DEFAULT_VOICE_ID, ELEVENLABS_MODEL, ELEVENLABS_FORMAT,
    SLACK_TINA_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SAM_BOT_TOKEN, SLACK_KAI_USER_ID, SLACK_SAM_USER_ID, SLACK_TINA_USER_ID,
    SLACK_CHANNEL, SLACK_CHANNEL_SAM, SLACK_CHANNEL_RESEARCH, SLACK_CHANNEL_AGENTS,
    SLACK_TRISTAN_BOT_TOKEN, SLACK_CHANNEL_TRISTAN, SLACK_TRISTAN_USER_ID,
    SLACK_CHARLIE_BOT_TOKEN, SLACK_CHARLIE_USER_ID,
    SLACK_CONNOR_BOT_TOKEN, SLACK_CHANNEL_CONNOR, SLACK_CONNOR_USER_ID,
)
from tina.agent import TinaAgent

_agent_lock = asyncio.Lock()

# ── Tool → dashboard panel mapping ────────────────────────────────────────────
_TOOL_TO_PANEL = {
    "get_weather":       "weather",
    "search":            "search",
    "news":              "news",
    "wikipedia":         "search",
    "vault_search":      "vault",
    "vault_read":        "vault",
    "list_events":       "calendar",
    "create_event":      "calendar",
    "update_event":      "calendar",
    "delete_event":      "calendar",
    "github_get_repo":   "github",
    "github_list_repos": "github",
    "github_list_issues":"github",
    "github_list_prs":   "github",
    "github_read_file":  "github",
    "read_backend_logs": "logs",
    "health_check":      "system",
    "restart_backend":   "system",
    "run_tests":         "system",
}
_TOOL_TTL = {
    "get_weather":  30000,
    "list_events":  25000, "create_event": 20000, "update_event": 15000,
    "search":       20000, "news": 20000, "wikipedia": 20000,
    "vault_search": 15000, "vault_read": 15000,
    "github_get_repo": 20000, "github_list_repos": 20000,
    "github_list_issues": 20000, "github_list_prs": 20000, "github_read_file": 20000,
    "read_backend_logs": 25000, "health_check": 15000,
    "restart_backend": 20000, "run_tests": 20000,
}

def _load_prefs() -> dict:
    from config import PREFS_FILE
    defaults = {"activity_log": True}
    if not os.path.exists(PREFS_FILE):
        return defaults
    try:
        return {**defaults, **_json.load(open(PREFS_FILE))}
    except Exception:
        return defaults


def _make_tool_result_event(name: str, result) -> dict | None:
    panel_type = _TOOL_TO_PANEL.get(name)
    if not panel_type:
        return None
    text = str(result) if not isinstance(result, str) else result
    if len(text) > 700:
        text = text[:700] + "…"
    return {
        "type":       "tool_result",
        "name":       name,
        "panel_type": panel_type,
        "text":       text,
        "ttl":        _TOOL_TTL.get(name, 15000),
    }

_AGENT_META = {
    "research": {"display": "Charlie",  "color": "#06b6d4", "glow": "#67e8f9", "channel": SLACK_CHANNEL_RESEARCH, "token": SLACK_CHARLIE_BOT_TOKEN  or None},
    "coding":   {"display": "Sam",      "color": "#10b981", "glow": "#6ee7b7", "channel": SLACK_CHANNEL_SAM,      "token": SLACK_SAM_BOT_TOKEN      or None},
    "email":    {"display": "Tristan",  "color": "#f59e0b", "glow": "#fcd34d", "channel": SLACK_CHANNEL_TRISTAN,  "token": SLACK_TRISTAN_BOT_TOKEN  or None},
    "data":     {"display": "Connor",   "color": "#8b5cf6", "glow": "#c4b5fd", "channel": SLACK_CHANNEL_CONNOR,   "token": SLACK_CONNOR_BOT_TOKEN   or None},
}

# Channel → agent key, for routing direct Slack messages to the right agent
_CHANNEL_TO_AGENT = {
    SLACK_CHANNEL_SAM:      "coding",
    SLACK_CHANNEL_RESEARCH: "research",
    SLACK_CHANNEL_TRISTAN:  "email",
    SLACK_CHANNEL_CONNOR:   "data",
}

# Slack user ID → agent key, for routing @mentions in #agents group chat
_USER_TO_AGENT = {
    uid: key for uid, key in [
        (SLACK_SAM_USER_ID,     "coding"),
        (SLACK_CHARLIE_USER_ID, "research"),
        (SLACK_TRISTAN_USER_ID, "email"),
        (SLACK_CONNOR_USER_ID,  "data"),
    ] if uid
}


async def _run_project_reindex():
    """Ask Sam to refresh the codebase index for every registered project."""
    from config import PROJECTS
    from tina.agents.coding import CodingAgent
    for project_name, project_path in PROJECTS.items():
        if not os.path.isdir(project_path):
            continue
        task = (
            f"Automated nightly codebase reindex — project: {project_name}\n\n"
            f"Project path: {project_path}\n\n"
            f"Write a comprehensive codebase index to the Obsidian vault at "
            f"01-Projects/{project_name}/codebase-index.md. Overwrite whatever is there.\n\n"
            f"IMPORTANT: Use fs_list with recursive=true on the project root — this gives you the "
            f"full file tree in one call and automatically skips node_modules, .git, __pycache__, "
            f"venv, dist, build, and other noise. Do NOT manually recurse into subdirectories.\n\n"
            f"The index must include:\n"
            f"1. Full file tree (one fs_list recursive call)\n"
            f"2. One-line description of every significant file\n"
            f"3. Key frameworks, patterns, and data models\n"
            f"4. Entry points and main flows\n\n"
            f"Read the files that define structure — config, models, routes, main components. "
            f"Write the index in a format that lets you start any task on this codebase "
            f"without reading files again."
        )
        print(f"[Nightly reindex] Starting for {project_name}...")
        asyncio.create_task(_run_agent_background("coding", CodingAgent, task, None))
        await asyncio.sleep(120)  # stagger projects so they don't run in parallel


async def _schedule_nightly_reindex():
    """Fires at 2 AM each night."""
    while True:
        now    = datetime.now()
        target = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await _run_project_reindex()


async def _run_morning_briefing():
    """Gather live data and deliver Tina's spoken morning briefing via TTS + Slack."""
    from datetime import date
    from config import PENDING_TASKS_DIR

    today     = date.today()
    today_str = today.strftime("%A, %d %B %Y")
    today_iso = today.isoformat()
    sections  = []

    # Weather
    try:
        w = await asyncio.to_thread(
            _DIRECT_HANDLERS["get_weather"], "get_weather", {"location": "Sydney"}
        )
        sections.append(f"WEATHER:\n{w}")
    except Exception as e:
        print(f"[briefing] weather: {e}")

    # Today's calendar events
    try:
        cal = await asyncio.to_thread(
            _DIRECT_HANDLERS["list_events"], "list_events", {
                "time_min": f"{today_iso}T00:00:00",
                "time_max": f"{today_iso}T23:59:59",
                "max_results": 10,
            }
        )
        sections.append(f"CALENDAR — {today_str}:\n{cal}")
    except Exception as e:
        print(f"[briefing] calendar: {e}")

    # Pending agent tasks still on disk
    try:
        if os.path.isdir(PENDING_TASKS_DIR):
            pending = [f for f in os.listdir(PENDING_TASKS_DIR) if f.endswith(".json")]
            if pending:
                lines = []
                for fname in pending[:5]:
                    try:
                        with open(os.path.join(PENDING_TASKS_DIR, fname)) as f:
                            spec = _json.load(f)
                        lines.append(f"  • {spec.get('agent_key','?')}: {spec.get('task','')[:80]}")
                    except Exception:
                        pass
                if lines:
                    sections.append("PENDING AGENT TASKS:\n" + "\n".join(lines))
    except Exception as e:
        print(f"[briefing] pending tasks: {e}")

    # Vault — urgent / priority / deadline notes
    try:
        v = await asyncio.to_thread(
            _DIRECT_HANDLERS["vault_search"], "vault_search",
            {"query": "urgent priority deadline today"}
        )
        if v and "no results" not in str(v).lower() and "not configured" not in str(v).lower():
            sections.append(f"VAULT — FLAGGED:\n{str(v)[:500]}")
    except Exception as e:
        print(f"[briefing] vault: {e}")

    # Ask Claude to synthesise a natural spoken briefing
    data_block = f"Today is {today_str}.\n\n" + "\n\n".join(sections)
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp   = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=350,
            system=(
                "You are TINA giving Ky his morning briefing. "
                "Write a natural spoken summary — plain prose only, no markdown, no bullet points, no headers. "
                "Be warm and direct. Cover: weather, what's on the calendar, any pending agent work. "
                "If the calendar is empty, say so. "
                "Keep it under 100 words. Start with 'Good morning Ky.' "
                "End with one sentence on what to focus on first today."
            ),
            messages=[{"role": "user", "content": data_block}],
        )
        briefing = next((b.text for b in resp.content if hasattr(b, "text")), "")
    except Exception as e:
        print(f"[briefing] synthesis failed: {e}")
        briefing = f"Good morning Ky. Today is {today_str}. I had trouble pulling the full briefing — check Slack for anything urgent."

    if not briefing.strip():
        return

    print(f"[briefing] {briefing}")

    # Speak it
    await broadcast({"type": "response", "text": briefing})
    await _tts_stream(briefing)

    # Post to Slack — spoken text up top, raw data below for reference
    kai_mention = f"<@{SLACK_KAI_USER_ID}>" if SLACK_KAI_USER_ID else "Ky"
    raw_data    = "\n\n".join(sections)[:1500] if sections else ""
    slack_body  = f"*Morning briefing — {today_str}* {kai_mention}\n\n{briefing}"
    if raw_data:
        slack_body += f"\n\n```\n{raw_data}\n```"
    await _slack_post(SLACK_CHANNEL, slack_body, token=SLACK_TINA_BOT_TOKEN)


async def _run_startup_briefing():
    """
    Deliver the morning briefing once per calendar day — triggered on first
    server startup after midnight rather than at a fixed clock time.
    Tracks delivery in data/briefing_date.txt so restarts later in the day skip it.
    """
    from datetime import date
    from config import BRIEFING_STATE_FILE

    today = date.today().isoformat()

    try:
        if os.path.exists(BRIEFING_STATE_FILE):
            if open(BRIEFING_STATE_FILE).read().strip() == today:
                print(f"[briefing] already delivered today ({today}) — skipping")
                return
    except Exception:
        pass

    # Small delay so the Slack connection has time to establish before we post
    await asyncio.sleep(6)

    try:
        await _run_morning_briefing()
        with open(BRIEFING_STATE_FILE, "w") as f:
            f.write(today)
    except Exception as e:
        print(f"[briefing] startup briefing failed: {e}")


async def _post_restart_announcement():
    """If this startup was triggered by a self-restart, notify Ky on Slack."""
    from config import BASE_DIR
    sentinel = os.path.join(BASE_DIR, "data", "post_restart.json")
    if not os.path.exists(sentinel):
        return
    try:
        with open(sentinel) as f:
            data = _json.load(f)
        os.remove(sentinel)
        reason = data.get("reason", "code or config change")
        kai_mention = f"<@{SLACK_KAI_USER_ID}>" if SLACK_KAI_USER_ID else "@Ky"
        msg = f"{kai_mention} — I restarted successfully. Reason: {reason}. Everything looks good."
        await asyncio.sleep(2)  # give Slack connection time to establish
        await _slack_post(SLACK_CHANNEL_AGENTS, msg, token=SLACK_TINA_BOT_TOKEN)
    except Exception as e:
        print(f"[lifespan] post-restart announcement failed: {e}")


async def _drain_preview_queue():
    """Drain fs_write events and broadcast them to all connected dashboards."""
    import queue as _queue
    from tools import filesystem_tool as _ft
    while True:
        await asyncio.sleep(0.1)
        while True:
            try:
                item = _ft._preview_queue.get_nowait()
                await broadcast({"type": "code_preview", "path": item["path"], "content": item["content"]})
            except _queue.Empty:
                break


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_start_slack())
    asyncio.create_task(_schedule_nightly_reindex())
    asyncio.create_task(_run_startup_briefing())
    asyncio.create_task(_post_restart_announcement())
    asyncio.create_task(_drain_preview_queue())
    asyncio.create_task(_resume_pending_tasks())
    yield


app = FastAPI(title="TINA Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: list[WebSocket] = []

# Per-agent queues for Ky's direct replies in agent channels
_agent_answer_queues: dict[str, asyncio.Queue] = {}
_channel_name_cache:  dict[str, str]           = {}  # channel ID → "#name"


async def broadcast(data: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


# ── Background agent runner ───────────────────────────────────────────────────

def _make_slack_client(token: str | None = None):
    from slack_sdk import WebClient
    return WebClient(token=token or SLACK_TINA_BOT_TOKEN)


async def _slack_post(channel: str, message: str, token: str | None = None):
    """Post to Slack using the provided token (agent-specific) or fall back to Tina's token."""
    def _post():
        _make_slack_client(token).chat_postMessage(channel=channel, text=message)
    try:
        await asyncio.to_thread(_post)
    except Exception as e:
        print(f"[Slack] post to {channel} failed: {e}")


async def _resolve_channel_name(channel_id: str) -> str:
    """Resolve a Slack channel ID to its #name, with caching."""
    if channel_id in _channel_name_cache:
        return _channel_name_cache[channel_id]
    try:
        def _fetch():
            from slack_sdk import WebClient
            info = WebClient(token=SLACK_TINA_BOT_TOKEN).conversations_info(channel=channel_id)
            return "#" + info["channel"]["name"]
        name = await asyncio.to_thread(_fetch)
        _channel_name_cache[channel_id] = name
        return name
    except Exception:
        return channel_id


async def _get_tina_answer(question: str) -> str:
    """Answer a clarifying question from an agent using Tina's current conversation context."""
    try:
        client   = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        messages = list(agent.history) + [{
            "role":    "user",
            "content": (
                f"One of your specialist agents has a clarifying question:\n\n{question}\n\n"
                "Answer directly and concisely. If you genuinely don't know, say so and tell the agent to use its best judgement."
            ),
        }]
        response = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return next((b.text for b in response.content if hasattr(b, "text")), "")
    except Exception as e:
        print(f"[_get_tina_answer] error: {e}")
        return "I couldn't get a clear answer right now — use your best judgement and proceed."


_ESCALATE_SYSTEM = """You decide whether an agent's question requires the user's direct input or can be answered automatically.

Respond with exactly one word: ESCALATE or AUTO.

ESCALATE for:
- Deleting or overwriting files, data, or records
- Sending messages, emails, or notifications to external people
- Financial transactions or purchases
- Pushing to production, merging PRs, deploying
- Any action that cannot be easily undone
- Anything that affects people outside this system

AUTO for:
- Code architecture and design decisions
- UI/UX style and preference choices
- Technical stack or library choices
- File naming, structure, organisation
- Anything easily reversible
- Anything Tina can determine from user history and preferences"""


async def _should_escalate_to_kai(question: str) -> bool:
    """Return True if this question needs Ky's direct input rather than Tina's auto-answer."""
    try:
        client   = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=10,
            system=_ESCALATE_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        text = next((b.text for b in response.content if hasattr(b, "text")), "AUTO")
        return "ESCALATE" in text.upper()
    except Exception as e:
        print(f"[escalate] classification error: {e}")
        return False  # default to auto on error


_AGENT_PERSONAS = {
    "Sam":     "You are Sam — a dry, goofy but technically sharp coding agent.",
    "Charlie": "You are Charlie — a thorough, curious research agent who is precise about sources.",
    "Tristan": "You are Tristan — a precise, professional email agent. You are measured and clear, never casual.",
    "Connor":  "You are Connor — an analytical data agent who is direct and numbers-focused.",
}

def _agent_persona(display: str) -> str:
    return _AGENT_PERSONAS.get(display, f"You are {display}, a specialist AI agent.")


async def _sam_acknowledgment(task: str, display: str = "Sam") -> str:
    """Agent 'on it' reply before work starts."""
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            system=(
                f"{_agent_persona(display)} "
                "Write a single short acknowledgment (under 15 words) that you're starting the task. "
                "Be natural, in character. No preamble. No sign-off."
            ),
            messages=[{"role": "user", "content": f"Task: {task[:150]}"}],
        )
        return next((b.text for b in resp.content if hasattr(b, "text")), "On it.")
    except Exception:
        return "On it."


async def _sam_completion_msg(task: str, result: str, tina_mention: str, display: str = "Sam") -> str:
    """Agent '@Tina done' completion message."""
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            system=(
                f"{_agent_persona(display)} "
                f"Write a short completion message starting with '{tina_mention}' (max 25 words). "
                "Say you're done and mention specifically what was completed (key outcomes, recipients, file names, etc.). "
                "In character. No preamble."
            ),
            messages=[{"role": "user", "content": f"Task: {task[:100]}\nResult: {result[:400]}"}],
        )
        return next((b.text for b in resp.content if hasattr(b, "text")), f"{tina_mention} done.")
    except Exception:
        return f"{tina_mention} done."


async def _tina_verbal_summary(display: str, result: str) -> str:
    """Short spoken sentence for Tina to say to Ky when a background agent finishes."""
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system=(
                "You are Tina. Write ONE short spoken sentence (plain prose, no markdown, under 20 words) "
                f"telling Ky that {display} just finished. Mention specifically what was built or changed. "
                "Casual, warm, direct."
            ),
            messages=[{"role": "user", "content": result[:400]}],
        )
        return next((b.text for b in resp.content if hasattr(b, "text")), f"{display} just finished.")
    except Exception:
        return f"{display} just finished."


async def _agent_verify_response(display: str, task: str, result: str) -> tuple[bool, str]:
    """
    Verify task completion. First does a fast text scan for known failure signals
    in the tail of the result (where conclusions live), then falls back to a Haiku
    self-assessment if no hard signals are found.
    Returns (completed: bool, agent_message: str)
    """
    # Fast fail: scan the last 600 chars for definitive failure signals
    _FAIL_SIGNALS = [
        "i couldn't", "i was unable", "i cannot", "failed to complete",
        "did not complete", "unable to finish", "could not be completed",
        "api error", "connection refused", "timed out", "authentication failed",
        "no such file", "permission denied", "traceback (most recent",
    ]
    tail = result.lower()[-600:]
    for sig in _FAIL_SIGNALS:
        if sig in tail:
            return False, f"Task incomplete — result ends with failure signal: \"{sig}\". Check the full output."

    # Suspiciously short result for a real task
    if len(result.strip()) < 80 and len(task) > 300:
        return False, "Result is too short for this task — likely incomplete or crashed early."

    # Haiku self-assessment as the final check
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=(
                "You are a task-completion auditor for an AI assistant system. "
                "You will be given a task brief and the output log produced by a specialist agent that ran it. "
                "Your job is to assess whether the output log shows the task was completed successfully.\n\n"
                "Look for: explicit success confirmation, expected outputs present, no error messages, "
                "no 'failed', 'unable', 'could not', or 'timed out' in the log tail.\n\n"
                'Respond with JSON only: {"completed": true/false, "message": "1-2 sentence summary for Tina"}\n\n'
                "If completed: state what the log confirms was done (recipients, files, outcomes).\n"
                "If failed or partial: state what the log shows went wrong.\n"
                "Do NOT question whether the actions were possible — trust the log. Be direct. No preamble."
            ),
            messages=[{"role": "user", "content": f"Task brief: {task[:400]}\n\nAgent output log: {result[:600]}"}],
        )
        text = next((b.text for b in resp.content if hasattr(b, "text")), "")
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = _json.loads(match.group())
            return bool(data.get("completed", True)), str(data.get("message", "Looks good."))
    except Exception as e:
        print(f"[verify] {display} verification error: {e}")
    return True, "Looks good from my end."


# ── Pending-task persistence (survive restarts) ───────────────────────────────

def _save_pending_task(task_id: str, agent_key: str, task: str) -> None:
    from config import PENDING_TASKS_DIR
    os.makedirs(PENDING_TASKS_DIR, exist_ok=True)
    with open(os.path.join(PENDING_TASKS_DIR, f"{task_id}.json"), "w") as f:
        _json.dump({"task_id": task_id, "agent_key": agent_key, "task": task,
                    "started_at": datetime.now().isoformat()}, f)

def _clear_pending_task(task_id: str) -> None:
    from config import PENDING_TASKS_DIR
    try:
        os.remove(os.path.join(PENDING_TASKS_DIR, f"{task_id}.json"))
    except FileNotFoundError:
        pass

async def _resume_pending_tasks() -> None:
    """On startup, re-dispatch any tasks that were interrupted by a prior restart."""
    from config import PENDING_TASKS_DIR
    from tina.agent import _AGENTS
    if not os.path.isdir(PENDING_TASKS_DIR):
        return
    files = [f for f in os.listdir(PENDING_TASKS_DIR) if f.endswith(".json")]
    if not files:
        return
    await asyncio.sleep(4)  # let Slack connection establish first
    for fname in files:
        path = os.path.join(PENDING_TASKS_DIR, fname)
        try:
            with open(path) as f:
                spec = _json.load(f)
            agent_key = spec["agent_key"]
            task      = spec["task"]
            task_id   = spec["task_id"]
            cls       = _AGENTS.get(agent_key)
            if not cls:
                print(f"[resume] Unknown agent '{agent_key}' in {fname} — removing")
                os.remove(path)
                continue
            meta    = _AGENT_META.get(agent_key, {})
            channel = meta.get("channel", SLACK_CHANNEL)
            print(f"[resume] Resuming interrupted {agent_key} task: {task[:60]}...")
            await _slack_post(channel, "_Resuming after restart — picking up where I left off._",
                              token=meta.get("token"))
            asyncio.create_task(_run_agent_background(agent_key, cls, task, None,
                                                      task_id=task_id, retried=True))
        except Exception as e:
            print(f"[resume] Failed to resume {fname}: {e}")


async def background_runner(agent_key: str, cls, task: str, on_tool):
    """Called by TinaAgent._dispatch — persists the task then launches it."""
    task_id = str(uuid.uuid4())
    _save_pending_task(task_id, agent_key, task)
    asyncio.create_task(_run_agent_background(agent_key, cls, task, on_tool, task_id=task_id))


async def _run_agent_background(agent_key: str, cls, task: str, on_tool,
                                task_id: str = None, retried: bool = False):
    """Runs a specialist agent independently with Slack as the conversation channel."""
    from tina.agent_state import start_task, record_tool, end_task, summarize_input

    meta        = _AGENT_META.get(agent_key, {"display": agent_key, "color": "#8B5CF6", "glow": "#A78BFA", "channel": SLACK_CHANNEL, "token": None})
    display     = meta["display"]
    channel     = meta.get("channel", SLACK_CHANNEL)
    agent_token = meta.get("token")
    tina_token  = SLACK_TINA_BOT_TOKEN

    # Build @mention for whichever agent is running (not always Sam)
    _agent_uid   = {
        "coding":   SLACK_SAM_USER_ID,
        "research": SLACK_CHARLIE_USER_ID,
        "email":    SLACK_TRISTAN_USER_ID,
        "data":     SLACK_CONNOR_USER_ID,
    }.get(agent_key, "")
    sam_mention   = f"<@{SLACK_SAM_USER_ID}>"  if SLACK_SAM_USER_ID  else "@Sam"
    agent_mention = f"<@{_agent_uid}>"          if _agent_uid          else f"@{display}"
    tina_mention  = f"<@{SLACK_TINA_USER_ID}>" if SLACK_TINA_USER_ID else "@Tina"
    kai_mention   = f"<@{SLACK_KAI_USER_ID}>"  if SLACK_KAI_USER_ID  else "@Ky"

    async def tracking_on_tool(name: str, inputs: dict = None):
        record_tool(agent_key, name, summarize_input(name, inputs or {}))
        if on_tool:
            await on_tool(name, inputs)

    async def tracking_on_tool_result(name: str, inputs: dict, result):
        event = _make_tool_result_event(name, result)
        if event:
            await broadcast(event)

    async def question_handler(question: str) -> str:
        await _slack_post(channel, question, token=agent_token)
        escalate, tina_answer = await asyncio.gather(
            _should_escalate_to_kai(question),
            _get_tina_answer(question),
        )
        if not escalate:
            await _slack_post(channel, tina_answer, token=tina_token)
            return tina_answer
        # Register queue BEFORE posting to Slack — prevents a reply arriving
        # before the queue is ready (race condition that silently drops answers).
        q: asyncio.Queue = asyncio.Queue()
        _agent_answer_queues[channel] = q
        await _slack_post(
            channel,
            f"[ACTION REQUIRED] {kai_mention} — I need your call on this. Sam will wait.\n\n"
            f"_Tina's suggestion if you're unavailable: {tina_answer}_",
            token=tina_token,
        )
        try:
            kai_answer = await asyncio.wait_for(q.get(), timeout=14400)
            await _slack_post(channel, "Got it, thanks.", token=agent_token)
            return kai_answer
        except asyncio.TimeoutError:
            await _slack_post(channel, "No response after 4 hours — proceeding with Tina's suggestion.", token=agent_token)
            return tina_answer
        finally:
            _agent_answer_queues.pop(channel, None)

    async def plan_handler(plan: str) -> str:
        """Sam posts a plan — always routes to Ky for approval, never auto-answered."""
        plan_msg = (
            f"*Plan from {display}:*\n\n{plan}\n\n"
            f"_{kai_mention} — reply `approved` to proceed, or give feedback to redirect._"
        )
        # Register queue BEFORE posting to Slack — same race-condition fix as question_handler.
        q: asyncio.Queue = asyncio.Queue()
        _agent_answer_queues[channel] = q
        await _slack_post(channel, plan_msg, token=agent_token)
        await _slack_post(
            channel,
            f"{tina_mention} {kai_mention} — {display} has a plan ready. Waiting for your go-ahead.",
            token=tina_token,
        )
        try:
            feedback = await asyncio.wait_for(q.get(), timeout=86400)  # 24h
            await _slack_post(channel, f"Got it — proceeding.", token=agent_token)
            return feedback
        except asyncio.TimeoutError:
            await _slack_post(channel, "No response after 24 hours — proceeding with original plan.", token=agent_token)
            return "approved"
        finally:
            _agent_answer_queues.pop(channel, None)

    try:
        if not retried:
            # Step 1 — Tina @mentions the agent with the task brief
            await _slack_post(channel, f"{agent_mention}\n\n{task}", token=tina_token)

            # Step 2 — Agent acknowledges before starting work
            ack = await _sam_acknowledgment(task, display)
            await _slack_post(channel, ack, token=agent_token)

        start_task(agent_key, task)
        print(f"[{display}] background task started: {task[:80]}...")
        specialist = cls()
        result     = await specialist.run(task, on_tool=tracking_on_tool, on_tool_result=tracking_on_tool_result, question_handler=question_handler, plan_handler=plan_handler)

        print(f"[{display}] background task complete ({len(result)} chars)")

        # Step 3 — Agent @mentions Tina with a natural completion summary, then posts the full output
        completion_msg = await _sam_completion_msg(task, result, tina_mention, display)
        full_output = result[:2000] + (f"\n_(truncated — {len(result):,} chars total)_" if len(result) > 2000 else "")
        await _slack_post(channel, completion_msg, token=agent_token)
        await _slack_post(channel, full_output, token=agent_token)

        # Step 3b — Tina asks the agent to verify before reporting to Ky
        await _slack_post(
            channel,
            f"{agent_mention} Before I tell Ky — did that complete fully? Any issues I should flag?",
            token=tina_token,
        )
        completed, verify_msg = await _agent_verify_response(display, task, result)
        await _slack_post(channel, verify_msg, token=agent_token)

        # Step 4 — Report to Ky based on verification result
        if completed:
            verbal_summary = await _tina_verbal_summary(display, result)
            await _slack_post(SLACK_CHANNEL_AGENTS, f"{kai_mention} — {verbal_summary}", token=tina_token)
            summary = result[:300] + "…" if len(result) > 300 else result
            await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": summary})
            await broadcast({"type": "response", "text": verbal_summary})
            asyncio.create_task(_tts_stream(verbal_summary))
        else:
            issue_summary = f"{display} ran into an issue: {verify_msg}"
            await _slack_post(
                SLACK_CHANNEL_AGENTS,
                f"{kai_mention} — heads up, {display}'s task didn't complete fully. Check #agents for details.",
                token=tina_token,
            )
            await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": f"Issue: {verify_msg}"})
            await broadcast({"type": "response", "text": issue_summary})
            asyncio.create_task(_tts_stream(issue_summary))
            asyncio.create_task(_write_error_memory(agent_key, task, verify_msg))

    except asyncio.CancelledError:
        # Server is restarting — leave the task file so it gets re-dispatched on startup
        print(f"[{display}] background task cancelled (server restart) — will resume on next start")
        raise
    except Exception as e:
        print(f"[{display}] background task error: {e}")
        # Include what was completed before the crash so Ky knows where things stand
        from tina.agent_state import _progress
        completed_steps = _progress.get(agent_key, {}).get("history", [])
        steps_note = ""
        if completed_steps:
            step_lines = "\n".join(
                f"  • {s['tool']}: {s['summary']}" for s in completed_steps[-5:]
            )
            steps_note = f"\n\nCompleted {len(completed_steps)} step(s) before crash:\n{step_lines}"
        await _slack_post(channel, f"Hit an error: {e}{steps_note}", token=agent_token)
        err_summary = f"Error after {len(completed_steps)} steps: {e}"
        await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": err_summary})
        await broadcast({"type": "response", "text": f"{display} hit an error: {e}"})
    finally:
        end_task(agent_key)
        # Only clear the task file on normal completion/error, not on cancellation
        if task_id and not asyncio.current_task().cancelled():
            _clear_pending_task(task_id)


async def _direct_agent_chat(agent_key: str, text: str, channel: str):
    """Handle a direct message to an agent in their Slack channel."""
    from tina.agent import _AGENTS
    meta        = _AGENT_META.get(agent_key, {})
    agent_token = meta.get("token")
    cls         = _AGENTS.get(agent_key)
    if not cls:
        return
    try:
        specialist = cls()
        result     = await specialist.run(text)
        await _slack_post(channel, result[:2000], token=agent_token)
        if len(result) > 2000:
            await _slack_post(channel, f"_(response truncated — {len(result):,} chars total)_", token=agent_token)
    except Exception as e:
        await _slack_post(channel, f"Error: {e}", token=agent_token)


async def diag_runner():
    """Called by TinaAgent when Ky asks for a diagnostic."""
    from tina.diagnostics import CHECKS
    await broadcast({"type": "diag_start", "checks": [cid for cid, _ in CHECKS]})

    async def on_result(check_id, label, status, detail):
        await broadcast({"type": "diag_update", "id": check_id, "label": label, "status": status, "detail": detail})

    asyncio.create_task(_run_diagnostics_task(on_result))


# ── Agent instance (wired with background runner) ─────────────────────────────
agent      = TinaAgent(background_runner=background_runner, diag_runner=diag_runner)
_hud_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

_HUD_SYSTEM = """You are TINA's neural core generating live dashboard intelligence panels.
Respond ONLY with a JSON array of 2-4 element specs. No markdown, no explanation, raw JSON only.

Each element has:
- title: string (uppercase, max 14 chars)
- persistent: boolean (true = stays until cleared)
- ephemeral: number (ms, 4000-8000) if NOT persistent — omit if persistent
- type: one of: agent_grid | thought | memory_nodes | data_flow | confidence | bars | alert

Type-specific fields:
- agent_grid: agents:[{name:string, active:boolean}] — 4 items, mix active/idle
- thought: thoughts:[string] — 3 short inner-monologue fragments, first person
- memory_nodes: nodes:[string] — 5-6 short topic tags from recent context
- data_flow: label:string, bps:string (e.g. "2.4 KB/s")
- confidence: value:number (0-100), label:string
- bars: bars:[{label:string, value:number}] — 3 items, 0-100
- alert: message:string, level:"info"|"warn"|"error"

Mix persistent and ephemeral. Be creative and AI-system-appropriate."""


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm;codecs=opus") -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.deepgram.com/v1/listen",
            params={
                "model":        "nova-2",
                "language":     "en-AU",
                "smart_format": "true",
                "punctuate":    "true",
            },
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type":  mime_type,
            },
            content=audio_bytes,
        )
        if not r.is_success:
            raise RuntimeError(f"Deepgram {r.status_code}: {r.text[:200]}")
        result = r.json()
        return result["results"]["channels"][0]["alternatives"][0]["transcript"]


async def synthesise(text: str) -> bytes | None:
    if not ELEVENLABS_API_KEY or not text.strip():
        return None
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{DEFAULT_VOICE_ID}",
            params={"output_format": ELEVENLABS_FORMAT},
            headers={
                "xi-api-key":   ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={"text": text, "model_id": ELEVENLABS_MODEL},
        )
        if r.status_code == 200:
            return r.content
        print(f"[ElevenLabs] error {r.status_code}: {r.text[:200]}")
        return None


async def _pyttsx3_speak(text: str):
    """Play TTS through local PC speakers via pyttsx3."""
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            # Prefer a female voice for Tina
            female = next(
                (v for v in voices if any(n in v.name.lower() for n in ("zira", "aria", "female", "hazel"))),
                voices[0] if voices else None,
            )
            if female:
                engine.setProperty("voice", female.id)
            engine.setProperty("rate", 185)
            engine.setProperty("volume", 0.95)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[pyttsx3] error: {e}")
    await asyncio.to_thread(_speak)


async def _tts_stream(reply: str):
    """Split reply into sentences, TTS each one. ElevenLabs → browser; pyttsx3 fallback → speakers."""
    sentences = [s.strip() for s in _SENTENCE_RE.split(reply) if s.strip()]
    if not sentences:
        sentences = [reply.strip()]
    await broadcast({"type": "state", "state": "speaking"})

    if ELEVENLABS_API_KEY:
        any_audio = False
        for i, sentence in enumerate(sentences):
            audio = await synthesise(sentence)
            if audio:
                any_audio = True
                await broadcast({
                    "type":  "audio_chunk",
                    "index": i,
                    "data":  base64.b64encode(audio).decode(),
                })
        if not any_audio:
            print("[TTS] ElevenLabs returned nothing — falling back to pyttsx3")
            await _pyttsx3_speak(reply)
    else:
        await _pyttsx3_speak(reply)

    await broadcast({"type": "audio_end"})


async def _handle_message(text: str):
    """Shared logic for text input from both voice (STT) and typed messages."""
    await broadcast({"type": "state", "state": "thinking"})

    async def on_tool(name: str, inputs: dict = None):
        if name == "delegate_to_agent":
            key  = (inputs or {}).get("agent", "")
            meta = _AGENT_META.get(key, {"display": key.capitalize(), "color": "#8B5CF6", "glow": "#A78BFA"})
            event_type = "agent_background_start" if agent.has_background_runner else "agent_active"
            task_text = (inputs or {}).get("task", "")
            await broadcast({
                "type":  event_type,
                "agent": meta["display"],
                "key":   key,
                "color": meta["color"],
                "glow":  meta["glow"],
                "task":  task_text[:120] + "…" if len(task_text) > 120 else task_text,
            })
        else:
            await broadcast({"type": "tool", "name": name, "time": datetime.now().strftime("%H:%M:%S")})

    async def on_tool_result(name: str, inputs: dict, result):
        if name == "set_ui_pref":
            await broadcast({"type": "ui_pref", "key": inputs.get("key"), "value": inputs.get("value")})
            return
        event = _make_tool_result_event(name, result)
        if event:
            await broadcast(event)

    async def on_agent_done(agent_key: str):
        await broadcast({"type": "agent_done"})

    reply = await agent.chat(text, on_tool=on_tool, on_tool_result=on_tool_result, on_agent_done=on_agent_done, background=True)
    print(f"\n[TINA] {reply}\n")
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply, list(agent.history)))
    await _tts_stream(reply)


async def _write_memory(user_msg: str, tina_reply: str, history: list[dict]) -> None:
    from tina.memory import extract_and_write_notes
    await extract_and_write_notes(user_msg, tina_reply, history=history)


async def _write_error_memory(agent_key: str, task: str, issue: str) -> None:
    """Write a failure note to the vault so Sam doesn't repeat the same mistake."""
    from pathlib import Path
    from config import VAULT_DIR, PROJECTS
    import re as _re
    now      = datetime.now()
    today    = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # Find which project this task is about
    project = next((name for name in PROJECTS if name.lower() in task.lower()), "tina")
    slug    = _re.sub(r'[^a-z0-9]+', '-', issue[:40].lower()).strip('-')
    fname   = f"{today}-error-{slug}.md"
    folder  = Path(VAULT_DIR) / "01-Projects" / project / "Notes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / fname
    if path.exists():
        return
    content = (
        f"---\ndate: {today}\ntags: [tina-memory, error, {project}, {agent_key}]\n---\n\n"
        f"# Failed task: {issue[:60]}\n\n"
        f"**Agent:** {agent_key}\n"
        f"**Task:** {task[:300]}\n\n"
        f"**What went wrong:** {issue}\n\n"
        f"**Why this matters:** Sam should check for this pattern before attempting similar tasks "
        f"and avoid the approach that caused this failure.\n\n"
        f"[[01-Projects/{project}/CLAUDE]] · [[01-Projects/tina/CLAUDE|Sam]]\n\n"
        f"*Written by Tina · {time_str}*"
    )
    path.write_text(content, encoding="utf-8")


@app.post("/api/briefing")
async def trigger_briefing():
    """Manually trigger the morning briefing — bypasses the once-per-day state check."""
    asyncio.create_task(_run_morning_briefing())
    return {"ok": True, "message": "Morning briefing started."}


@app.get("/api/status")
async def get_status():
    from config import DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, GITHUB_TOKEN, TAVILY_API_KEY, OPENWEATHER_API_KEY
    return {
        "deepgram":    bool(DEEPGRAM_API_KEY),
        "elevenlabs":  bool(ELEVENLABS_API_KEY),
        "github":      bool(GITHUB_TOKEN),
        "tavily":      bool(TAVILY_API_KEY),
        "weather":     bool(OPENWEATHER_API_KEY),
    }


@app.post("/api/diagnostics")
async def run_diagnostics():
    """Trigger a full system diagnostic. Results stream to all connected dashboards via WebSocket."""
    from tina.diagnostics import CHECKS, run_all
    check_ids = [cid for cid, _ in CHECKS]
    await broadcast({"type": "diag_start", "checks": check_ids})

    async def on_result(check_id: str, label: str, status: str, detail: str):
        await broadcast({"type": "diag_update", "id": check_id, "label": label, "status": status, "detail": detail})

    asyncio.create_task(_run_diagnostics_task(on_result))
    return {"ok": True}


async def _run_diagnostics_task(on_result):
    from tina.diagnostics import run_all
    results: dict[str, dict] = {}

    async def collecting_result(check_id, label, status, detail):
        results[check_id] = {"label": label, "status": status, "detail": detail}
        await on_result(check_id, label, status, detail)

    try:
        await run_all(collecting_result)
    finally:
        await broadcast({"type": "diag_complete"})

    issues = [
        (r["label"], r["status"], r["detail"])
        for r in results.values()
        if r["status"] in ("fail", "warn")
    ]
    if issues:
        fail_count = sum(1 for _, s, _ in issues if s == "fail")
        warn_count = sum(1 for _, s, _ in issues if s == "warn")
        parts = []
        if fail_count: parts.append(f"{fail_count} failure{'s' if fail_count > 1 else ''}")
        if warn_count: parts.append(f"{warn_count} warning{'s' if warn_count > 1 else ''}")
        summary = " and ".join(parts)
        names   = ", ".join(label for label, _, _ in issues)
        speech  = f"Diagnostic complete. I found {summary} — {names}. I'm sending the details to Slack with recommended fixes."
        await broadcast({"type": "response", "text": speech})
        asyncio.create_task(_tts_stream(speech))
        asyncio.create_task(_diag_review(issues))
    else:
        speech = "All systems healthy. Everything passed."
        await broadcast({"type": "response", "text": speech})
        asyncio.create_task(_tts_stream(speech))


async def _diag_review(issues: list[tuple[str, str, str]]):
    """Review diagnostic issues — fix what's possible, notify Ky about the rest via Slack."""
    lines = "\n".join(f"{status.upper()}: {label} — {detail}" for label, status, detail in issues)
    prompt = (
        f"A system diagnostic just completed and found these issues:\n\n{lines}\n\n"
        "Write a brief Slack message for Ky summarising each issue and the exact action needed to fix it. "
        "Include relevant links (e.g. elevenlabs.io/subscription for credit issues). "
        "Be direct and specific. Plain text only, no markdown headers."
    )
    try:
        # Use a plain Anthropic call — no tools, no loop risk
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp   = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=512,
            system="You are Tina, a concise AI assistant. Write short, actionable Slack notifications.",
            messages=[{"role": "user", "content": prompt}],
        )
        review = next((b.text for b in resp.content if hasattr(b, "text")), "")
        if review:
            await _slack_post(SLACK_CHANNEL, f"*Diagnostic issues found:*\n\n{review}")
            print(f"[diag_review] posted to Slack: {review[:80]}...")
    except Exception as e:
        print(f"[diag_review] error: {e}")


@app.post("/api/spawn-hud")
async def spawn_hud():
    response = await _hud_client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=_HUD_SYSTEM,
        messages=[{"role": "user", "content": "Generate HUD elements now."}],
    )
    text = response.content[0].text.replace("```json", "").replace("```", "").strip()
    return _json.loads(text)


@app.post("/api/chat")
async def chat_endpoint(body: dict):
    """Shared chat entry point used by Slack and any other async callers."""
    text   = body.get("text", "").strip()
    source = body.get("source", "api")
    if not text:
        return {"reply": ""}
    label = f"[{source.upper()}] {text}"
    await broadcast({"type": "heard", "text": label})
    async with _agent_lock:
        # background=False: Slack waits for the full reply including any delegation
        reply = await agent.chat(text, background=False)
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply))
    asyncio.create_task(_tts_stream(reply))
    return {"reply": reply}


async def _start_slack():
    if not SLACK_TINA_BOT_TOKEN or not SLACK_APP_TOKEN:
        print("[Slack] Tokens not configured — Slack listener not started.")
        return
    try:
        from slack_bolt.async_app import AsyncApp as BoltApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        import httpx as _httpx

        bolt = BoltApp(token=SLACK_TINA_BOT_TOKEN)

        @bolt.message("")
        async def on_message(message, say, logger):
            text = message.get("text", "").strip()
            if not text or message.get("bot_id"):
                return

            # Resolve channel ID to name
            channel_id   = message.get("channel", "")
            channel_name = await _resolve_channel_name(channel_id)

            # Agent is waiting for Ky's reply (escalated question)
            if channel_name in _agent_answer_queues:
                await _agent_answer_queues[channel_name].put(text)
                return

            # Group chat in #agents — route @mentions to the mentioned agent
            if channel_name == SLACK_CHANNEL_AGENTS:
                for user_id, agent_key in _USER_TO_AGENT.items():
                    if f"<@{user_id}>" in text:
                        asyncio.create_task(_direct_agent_chat(agent_key, text, SLACK_CHANNEL_AGENTS))
                        return
                # No agent @mentioned — fall through to Tina

            # Direct message to an agent's own channel
            agent_key = _CHANNEL_TO_AGENT.get(channel_name)
            if agent_key:
                asyncio.create_task(_direct_agent_chat(agent_key, text, channel_name))
                return

            # Otherwise route to Tina
            try:
                async with _httpx.AsyncClient(timeout=120) as client:
                    r = await client.post(
                        "http://localhost:8000/api/chat",
                        json={"text": text, "source": "slack"},
                    )
                reply = r.json().get("reply", "")
                if reply:
                    await say(reply)
            except Exception as e:
                logger.error(f"Slack handler error: {e}")
                await say(f"Error: {e}")

        handler = AsyncSocketModeHandler(bolt, SLACK_APP_TOKEN)
        print("[Slack] Socket Mode listener starting...")
        await handler.start_async()
    except Exception as e:
        print(f"[Slack] Failed to start: {e}")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    await ws.send_json({"type": "state", "state": "listening"})
    await ws.send_json({"type": "prefs", "data": _load_prefs()})
    pending_mime = "audio/webm;codecs=opus"
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            # ── Binary frame: audio from browser mic ──────────────────────────
            if msg.get("bytes"):
                audio_bytes = msg["bytes"]
                print(f"[STT] received {len(audio_bytes)} bytes, mime={pending_mime}")
                if len(audio_bytes) < 512:
                    print("[STT] audio too short, ignoring")
                    await broadcast({"type": "state", "state": "listening"})
                    continue
                try:
                    transcript = await transcribe_audio(audio_bytes, pending_mime)
                    print(f"[STT] transcript: {repr(transcript)}")
                    if transcript.strip():
                        await broadcast({"type": "heard", "text": transcript})
                        await _handle_message(transcript)
                    else:
                        await broadcast({"type": "state", "state": "listening"})
                except Exception as e:
                    print(f"[STT] error: {e}")
                    await broadcast({"type": "response", "text": f"[STT error: {e}]"})
                    await broadcast({"type": "state", "state": "listening"})

            # ── Text frame: JSON control messages ─────────────────────────────
            elif msg.get("text"):
                data     = _json.loads(msg["text"])
                msg_type = data.get("type")

                if msg_type == "audio_meta":
                    pending_mime = data.get("mimeType", pending_mime)
                    print(f"[STT] mime type set to: {pending_mime}")

                elif msg_type == "message":
                    text = data.get("text", "").strip()
                    if not text:
                        continue
                    await broadcast({"type": "heard", "text": text})
                    await _handle_message(text)

                elif msg_type == "audio_done":
                    await broadcast({"type": "state", "state": "listening"})

                elif msg_type == "reset":
                    agent.reset()

    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)
