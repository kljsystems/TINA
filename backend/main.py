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
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import httpx
import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from config import (
    ANTHROPIC_API_KEY, MODEL, ORCHESTRATOR_MODEL, SYSTEM_PROMPT,
    DEEPGRAM_API_KEY, ELEVENLABS_API_KEY,
    DEFAULT_VOICE_ID, ELEVENLABS_MODEL, ELEVENLABS_FORMAT,
    VAULT_DIR,
    SLACK_TINA_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL, SLACK_KY_USER_ID,
    WAKE_WORD_ENABLED,
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
    defaults = {"activity_log": True, "gaming_mode": False}
    if not os.path.exists(PREFS_FILE):
        return defaults
    try:
        return {**defaults, **_json.load(open(PREFS_FILE))}
    except Exception:
        return defaults


def _save_prefs(prefs: dict) -> None:
    from config import PREFS_FILE
    try:
        os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
        with open(PREFS_FILE, "w") as f:
            _json.dump(prefs, f, indent=2)
    except Exception as e:
        print(f"[prefs] save failed: {e}")


# ── Gaming mode ────────────────────────────────────────────────────────────────
# When active TINA: pauses all background schedulers, stays silent (TTS muted),
# suppresses dashboard popup cards, and — once local inference exists — must skip
# any local GPU work so it never contends with a running game. Cloud calls still
# work, so direct chat (text on the dashboard) keeps functioning while gaming.
# Phase 1 = manual toggle + voice command. Auto game-detection is phase 2.
_gaming_mode: bool = False


def gaming_mode_active() -> bool:
    """Single source of truth for gaming mode.

    FUTURE: any local LLM / image-video generation backend must check this before
    running and either route to cloud or defer, so local GPU work never competes
    with a game for VRAM/compute.
    """
    return _gaming_mode


async def _set_gaming_mode(value: bool) -> None:
    """Flip gaming mode, persist it, tell the dashboard, and confirm to Ky.

    Enabling is silent (TTS is gated off the moment _gaming_mode flips True);
    disabling speaks the 'back online' confirmation since voice is on again.
    """
    global _gaming_mode
    changed       = (_gaming_mode != value)
    _gaming_mode  = value

    if changed:
        prefs = _load_prefs()
        prefs["gaming_mode"] = value
        _save_prefs(prefs)
        print(f"[gaming-mode] {'ENABLED — schedulers paused, voice muted, popups suppressed' if value else 'DISABLED — schedulers, voice and popups resumed'}")

    await broadcast({"type": "gaming_mode", "active": value})

    if changed:
        msg = ("Gaming mode on. I'll stay quiet and hold all background tasks until you're done."
               if value else
               "Gaming mode off. Voice and background tasks are back online.")
        await broadcast({"type": "response", "text": msg})
        await _tts_stream(msg)  # self-gates: silent while gaming mode is on


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
    "research":  {"display": "Charlie", "color": "#06b6d4", "glow": "#67e8f9"},
    "coding":    {"display": "Sam",     "color": "#10b981", "glow": "#6ee7b7"},
    "email":     {"display": "Tristan", "color": "#f59e0b", "glow": "#fcd34d"},
    "data":      {"display": "Connor",  "color": "#8b5cf6", "glow": "#c4b5fd"},
    "marketing": {"display": "Wade",    "color": "#ec4899", "glow": "#f9a8d4"},
    "website":   {"display": "Jamie",   "color": "#0ea5e9", "glow": "#7dd3fc"},
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
        if _gaming_mode:
            print("[nightly-reindex] skipped — gaming mode active")
            continue
        await _run_project_reindex()


async def _run_morning_briefing():
    """Morning routine: open calendar, send popup cards for each data source, then speak a briefing."""
    from datetime import date, timedelta
    from config import PENDING_TASKS_DIR
    import uuid as _uuid
    import time as _time

    today     = date.today()
    today_str = today.strftime("%A, %d %B %Y")
    today_iso = today.isoformat()
    sections  = []

    await broadcast({"type": "morning_routine_start"})
    print(f"[briefing] morning routine starting — {today_str}")

    # Helper: send a dashboard popup card
    async def _popup(title: str, content: str, color: str = "#8B5CF6", ttl: int = 90000):
        await broadcast({
            "type":    "featured_panel",
            "id":      str(_uuid.uuid4()),
            "title":   title,
            "content": content,
            "color":   color,
            "ttl":     ttl,
            "ts":      int(_time.time() * 1000),
        })

    # 1. Open Google Calendar in the browser immediately
    try:
        import webbrowser
        webbrowser.open("https://calendar.google.com")
        print("[briefing] opened calendar in browser")
    except Exception as e:
        print(f"[briefing] browser open failed: {e}")

    # 2. Weather
    try:
        w = await asyncio.to_thread(
            _DIRECT_HANDLERS["get_weather"], "get_weather", {"location": "Sydney"}
        )
        w_str = str(w)[:380]
        sections.append(f"WEATHER:\n{w_str}")
        await _popup("WEATHER", w_str, color="#38bdf8")
    except Exception as e:
        print(f"[briefing] weather: {e}")

    # 3. Today's calendar events
    try:
        cal = await asyncio.to_thread(
            _DIRECT_HANDLERS["list_events"], "list_events", {
                "time_min": f"{today_iso}T00:00:00",
                "time_max": f"{today_iso}T23:59:59",
                "max_results": 10,
            }
        )
        cal_str = str(cal)[:380]
        sections.append(f"CALENDAR — {today_str}:\n{cal_str}")
        await _popup(
            "TODAY",
            cal_str if "no events" not in cal_str.lower() else "No events scheduled today.",
            color="#60a5fa",
        )
    except Exception as e:
        print(f"[briefing] calendar: {e}")

    # 4. Stripe MRR + revenue
    try:
        from tools.stripe_tool import handle as _stripe_handle
        stripe_raw = await asyncio.to_thread(_stripe_handle, "stripe_overview", {})
        if stripe_raw and "not configured" not in str(stripe_raw).lower():
            stripe_str = str(stripe_raw)[:380]
            sections.append(f"STRIPE:\n{stripe_str}")
            await _popup("REVENUE", stripe_str, color="#4ade80")
    except Exception as e:
        print(f"[briefing] stripe: {e}")

    # 5. KAOS platform health
    try:
        from tools.kaos_tool import _kaos_overview
        kaos = await asyncio.to_thread(_kaos_overview)
        if kaos and "not configured" not in str(kaos).lower():
            kaos_str = str(kaos)[:380]
            sections.append(f"KAOS:\n{kaos_str}")
            # Colour based on content: red if errors/issues, amber if warnings, green if healthy
            kaos_color = "#ef4444" if any(w in kaos_str.lower() for w in ("error", "critical", "down")) \
                else "#f59e0b" if any(w in kaos_str.lower() for w in ("warning", "ticket", "issue")) \
                else "#4ade80"
            await _popup("KAOS", kaos_str, color=kaos_color)
    except Exception as e:
        print(f"[briefing] kaos: {e}")

    # 6. Pending agent tasks
    try:
        if os.path.isdir(PENDING_TASKS_DIR):
            pending = [f for f in os.listdir(PENDING_TASKS_DIR) if f.endswith(".json")]
            if pending:
                lines = []
                for fname in pending[:6]:
                    try:
                        with open(os.path.join(PENDING_TASKS_DIR, fname)) as f:
                            spec = _json.load(f)
                        lines.append(f"• {spec.get('agent_key','?').upper()}: {spec.get('task','')[:70]}")
                    except Exception:
                        pass
                if lines:
                    task_str = "\n".join(lines)
                    sections.append("PENDING TASKS:\n" + task_str)
                    await _popup("PENDING", task_str, color="#a78bfa")
    except Exception as e:
        print(f"[briefing] pending tasks: {e}")

    # 7. Vault — urgent / flagged notes
    try:
        v = await asyncio.to_thread(
            _DIRECT_HANDLERS["vault_search"], "vault_search",
            {"query": "urgent priority deadline today action required"}
        )
        if v and "no results" not in str(v).lower() and "not configured" not in str(v).lower():
            sections.append(f"VAULT — FLAGGED:\n{str(v)[:400]}")
    except Exception as e:
        print(f"[briefing] vault: {e}")

    # 8. Tomorrow's calendar
    try:
        tomorrow  = (today + timedelta(days=1)).isoformat()
        day_after = (today + timedelta(days=2)).isoformat()
        cal2 = await asyncio.to_thread(
            _DIRECT_HANDLERS["list_events"], "list_events", {
                "time_min": f"{tomorrow}T00:00:00",
                "time_max": f"{day_after}T23:59:59",
                "max_results": 5,
            }
        )
        if cal2 and "no events" not in str(cal2).lower():
            sections.append(f"TOMORROW:\n{cal2}")
    except Exception as e:
        print(f"[briefing] tomorrow calendar: {e}")

    # Synthesise spoken briefing from all gathered data
    data_block = f"Today is {today_str}.\n\n" + "\n\n".join(sections)
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp   = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=400,
            system=(
                "You are TINA giving Ky his morning briefing. "
                "Write a natural spoken summary — plain prose only, no markdown, no bullet points, no headers. "
                "Be warm and direct. Cover weather, today's calendar, revenue snapshot, KAOS status, and any pending work. "
                "If calendar is empty, say so. "
                "End with: 'Your top priorities today are' then 3 specific actions ranked by urgency. "
                "Under 130 words total. Start with 'Good morning Ky.'"
            ),
            messages=[{"role": "user", "content": data_block}],
        )
        briefing = next((b.text for b in resp.content if hasattr(b, "text")), "")
    except Exception as e:
        print(f"[briefing] synthesis failed: {e}")
        briefing = f"Good morning Ky. Today is {today_str}. Check the dashboard cards for your data — I had trouble synthesising the full briefing."

    if briefing.strip():
        print(f"[briefing] {briefing}")
        await broadcast({"type": "response", "text": briefing})
        await _tts_stream(briefing)

    await broadcast({"type": "morning_routine_end"})
    print(f"[briefing] complete — {today_str}")


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

    await asyncio.sleep(3)

    if _gaming_mode:
        print("[briefing] skipped startup briefing — gaming mode active")
        return

    try:
        await _run_morning_briefing()
        with open(BRIEFING_STATE_FILE, "w") as f:
            f.write(today)
    except Exception as e:
        print(f"[briefing] startup briefing failed: {e}")


async def _run_weekly_briefing():
    """Monday morning: dispatch Connor, Wade, and Tristan for a full weekly business report."""
    from datetime import date
    from tina.agents.data      import DataAgent
    from tina.agents.marketing import MarketingAgent
    from tina.agents.email     import EmailAgent

    today_str = date.today().strftime("%A, %d %B %Y")
    print(f"[weekly-briefing] starting for {today_str}")

    # Tina speaks a short kickoff while agents run in background
    kickoff = (
        f"Good morning Ky. It's Monday — weekly briefing time. "
        "I've asked Connor to pull the business numbers, Wade to plan this week's content, "
        "and Tristan to summarise the inbox. I'll let you know as each one comes back."
    )
    await broadcast({"type": "response", "text": kickoff})
    await _tts_stream(kickoff)

    week_str = date.today().strftime("week of %d %B %Y")

    # Connor — business metrics
    await background_runner(
        "data", DataAgent,
        f"WEEKLY BUSINESS REPORT — {week_str}\n\n"
        "Pull and summarise all available business metrics for this week:\n"
        "1. Stripe: call stripe_overview for MRR, active subscriptions, past-due, and 30-day revenue\n"
        "2. KAOS platform: call kaos_overview for live user count, waitlist, subscriptions, and open support tickets\n"
        "3. Facebook: call meta_page_analytics (period=week) for impressions, reach, engaged users, and top posts\n"
        "4. Instagram: call meta_instagram_analytics (days=7) for impressions, reach, and top posts\n"
        "5. Meta Ads: call meta_ads_overview (period=last_7_days) if ads are running\n"
        "6. Any financial summaries or spreadsheets in Generated Docs/Connor/\n"
        "7. Compare against prior week if prior data exists in the vault\n"
        "Write a concise business summary: top-line numbers, week-on-week change, any anomalies. "
        "Save to vault at 02-Tina-Memory/Agents/Connor/ and report back.",
        None,
    )

    # Wade — weekly content plan
    await background_runner(
        "marketing", MarketingAgent,
        f"WEEKLY CONTENT PLAN — {week_str}\n\n"
        "Start by reviewing last week's performance: call meta_page_analytics and meta_instagram_analytics "
        "to see which posts got the most engagement. Note the top performer and why it likely worked.\n\n"
        "Then research what's trending this week in the tech/AI/business space relevant to KLJ Systems. "
        "Propose a content plan for the week: 3-5 post ideas across Facebook and Instagram with hooks, "
        "angles, and recommended formats — informed by what performed well last week. "
        "Save to vault at 02-Tina-Memory/Agents/Wade/ and report back.",
        None,
    )

    # Tristan — inbox summary
    await background_runner(
        "email", EmailAgent,
        f"WEEKLY INBOX SUMMARY — {week_str}\n\n"
        "Review the last 7 days of emails across all accounts (personal, business_outlook). "
        "Summarise: total received, key threads that need follow-up, anyone who hasn't been replied to, "
        "and any recurring senders or topics. Save notes to vault at 02-Tina-Memory/Agents/Tristan/ and report back.",
        None,
    )

    print(f"[weekly-briefing] all agents dispatched for {today_str}")


async def _schedule_weekly_briefing():
    """Fire the weekly briefing every Monday morning after the daily briefing."""
    from datetime import date
    WEEKLY_BRIEFING_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "weekly_briefing_date.txt"
    )
    WEEKLY_BRIEFING_FILE = os.path.normpath(WEEKLY_BRIEFING_FILE)

    while True:
        await asyncio.sleep(60)  # check every minute
        if _gaming_mode:
            continue
        now  = datetime.now()
        today = date.today()

        # Only fire on Monday (weekday 0) after 7am
        if now.weekday() != 0 or now.hour < 7:
            continue

        week_key = today.strftime("%Y-W%W")
        try:
            if os.path.exists(WEEKLY_BRIEFING_FILE):
                if open(WEEKLY_BRIEFING_FILE).read().strip() == week_key:
                    await asyncio.sleep(3600)  # already ran this week — check again in an hour
                    continue
        except Exception:
            pass

        try:
            await _run_weekly_briefing()
            os.makedirs(os.path.dirname(WEEKLY_BRIEFING_FILE), exist_ok=True)
            with open(WEEKLY_BRIEFING_FILE, "w") as f:
                f.write(week_key)
        except Exception as e:
            print(f"[weekly-briefing] failed: {e}")

        await asyncio.sleep(3600)  # don't re-check for an hour after running


async def _run_email_triage():
    """Dispatch Tristan to autonomously triage all inboxes."""
    from tina.agents.email import EmailAgent
    from datetime import date

    print(f"[email-triage] starting autonomous triage — {date.today().isoformat()}")

    task = (
        "AUTONOMOUS TRIAGE MODE — you are running on a scheduled basis without a human in the loop.\n\n"
        "For each account (personal, business_gmail, business_outlook):\n"
        "1. email_list to get unread emails (limit 50)\n"
        "2. Classify each email into:\n"
        "   - IGNORE: newsletters, marketing, automated notifications, social alerts\n"
        "   - RECEIPT: invoices, order confirmations, payment receipts — no reply needed\n"
        "   - LOW: FYI, cc'd threads, things worth knowing but no reply needed\n"
        "   - NORMAL: needs a reply but not time-sensitive\n"
        "   - URGENT: time-sensitive, from an important contact, or requires immediate action\n"
        "3. For IGNORE emails: email_mark_read + email_move folder='Newsletters'\n"
        "4. For RECEIPT emails: email_mark_read + email_label add=['Finance'] + email_move folder='Receipts'\n"
        "5. For LOW emails: email_mark_read + email_label add=['Low Priority']\n"
        "6. For NORMAL emails: email_label add=['Needs Reply'] — draft a reply and save it\n"
        "7. For URGENT emails: email_label add=['URGENT', 'Needs Reply'] — draft a reply and save it\n\n"
        "At the end, produce a triage report:\n"
        "- Total emails reviewed per account\n"
        "- IGNORED + RECEIPT (count + brief list)\n"
        "- LOW (count + brief list)\n"
        "- NORMAL — needs reply (sender, subject, your drafted reply)\n"
        "- URGENT — needs reply (sender, subject, your drafted reply, why it's urgent)\n\n"
        "Save the full triage report to vault at 02-Tina-Memory/Agents/Tristan/ "
        f"with filename {date.today().isoformat()}-triage.md\n\n"
        "Your completion report should be a spoken-friendly summary Tina can read aloud: "
        "how many emails, how many cleared, how many need attention."
    )

    await background_runner("email", EmailAgent, task, None)
    print("[email-triage] Tristan dispatched")


async def _schedule_email_triage():
    """Run email triage at 8am and 2pm daily."""
    TRIAGE_HOURS = {8, 14}
    _triage_done = set()  # tracks "YYYY-MM-DD-HH" keys already run

    while True:
        await asyncio.sleep(60)
        if _gaming_mode:
            continue
        now = datetime.now()
        key = now.strftime("%Y-%m-%d-") + str(now.hour)

        if now.hour in TRIAGE_HOURS and key not in _triage_done:
            _triage_done.add(key)
            # Keep set small — discard keys older than today
            today_prefix = now.strftime("%Y-%m-%d")
            _triage_done = {k for k in _triage_done if k.startswith(today_prefix)}
            try:
                await _run_email_triage()
            except Exception as e:
                print(f"[email-triage] scheduler error: {e}")


# ── Inbox pipeline utilities ──────────────────────────────────────────────────

_VAULT_ROOT   = Path(VAULT_DIR)
_INBOX_DIR    = _VAULT_ROOT / "00-Inbox"
_PROPOSED_DIR = _VAULT_ROOT / "01-Projects" / "Proposed"
_ACTIONS_DIR  = _VAULT_ROOT / "02-Tina-Memory" / "Actions"
_IDEAS_DIR    = _VAULT_ROOT / "02-Tina-Memory" / "Ideas"
_RESOURCES_DIR= _VAULT_ROOT / "03-Resources"

_CLASSIFY_PROMPT = """Classify this captured note. Output ONLY valid JSON — no markdown fences, no other text.

Classification options:
- "project": multi-step work requiring agents or significant effort spanning days or weeks
- "action": a single quick task for one person or agent
- "idea": concept or inspiration for future consideration, not immediately actionable
- "reference": information to store for future lookup — not a task
- "escalate": unclear or genuinely requires human judgment to classify

Output exactly this JSON:
{"classification": "project|action|idea|reference|escalate", "title": "short title in 5-8 words", "reasoning": "one sentence"}"""


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse simple YAML frontmatter. Returns (metadata_dict, body)."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---\n", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body    = content[end + 5:]
    metadata: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            metadata[key.strip()] = val.strip()
    return metadata, body


def _write_frontmatter(metadata: dict, body: str) -> str:
    fm_lines = [f"{k}: {v}" for k, v in metadata.items()]
    return "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body.lstrip()


def _safe_slug(title: str) -> str:
    """Convert a title to a safe folder/filename slug."""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:60]


async def _run_inbox_classifier():
    """Classify all unprocessed items in 00-Inbox/ using Haiku."""
    _INBOX_DIR.mkdir(parents=True, exist_ok=True)
    unprocessed = [
        f for f in _INBOX_DIR.glob("*.md")
        if _parse_frontmatter(f.read_text(encoding="utf-8"))[0].get("status") == "unprocessed"
    ]
    if not unprocessed:
        return

    print(f"[inbox-classifier] {len(unprocessed)} item(s) to classify")
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    from config import MODEL as HAIKU_MODEL
    for filepath in unprocessed:
        try:
            raw = filepath.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)

            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=_CLASSIFY_PROMPT,
                messages=[{"role": "user", "content": body.strip()[:2000]}],
            )
            text = next((b.text for b in resp.content if hasattr(b, "text")), "{}")
            decision = _json.loads(text)

            meta["status"]         = "classified"
            meta["classification"] = decision.get("classification", "escalate")
            meta["title"]          = decision.get("title", filepath.stem)
            meta["reasoning"]      = decision.get("reasoning", "")
            filepath.write_text(_write_frontmatter(meta, body), encoding="utf-8")
            print(f"[inbox-classifier] {filepath.name} → {meta['classification']}: {meta['title']}")
        except Exception as e:
            print(f"[inbox-classifier] failed on {filepath.name}: {e}")


async def _run_inbox_router():
    """Route classified inbox items to the correct vault folders."""
    classified = [
        f for f in _INBOX_DIR.glob("*.md")
        if _parse_frontmatter(f.read_text(encoding="utf-8"))[0].get("status") == "classified"
    ]
    if not classified:
        return

    from tina.agents.research import ResearchAgent

    for filepath in classified:
        try:
            raw          = filepath.read_text(encoding="utf-8")
            meta, body   = _parse_frontmatter(raw)
            classification = meta.get("classification", "escalate")
            title          = meta.get("title", filepath.stem)
            slug           = _safe_slug(title)
            date_prefix    = meta.get("date", datetime.now().isoformat())[:10]
            new_filename   = f"{date_prefix}-{slug}.md"

            if classification == "project":
                dest_dir = _PROPOSED_DIR / slug
                dest_dir.mkdir(parents=True, exist_ok=True)
                meta["status"] = "proposed"
                dest = dest_dir / "capture.md"
                dest.write_text(_write_frontmatter(meta, body), encoding="utf-8")
                filepath.unlink()
                print(f"[inbox-router] {title} → 01-Projects/Proposed/{slug}/")

                # Auto-dispatch Charlie to research this project
                asyncio.create_task(_auto_research_project(slug, title, body.strip()))

            elif classification == "action":
                _ACTIONS_DIR.mkdir(parents=True, exist_ok=True)
                meta["status"] = "routed"
                dest = _ACTIONS_DIR / new_filename
                dest.write_text(_write_frontmatter(meta, body), encoding="utf-8")
                filepath.unlink()
                print(f"[inbox-router] {title} → 02-Tina-Memory/Actions/")

            elif classification == "idea":
                _IDEAS_DIR.mkdir(parents=True, exist_ok=True)
                meta["status"] = "routed"
                dest = _IDEAS_DIR / new_filename
                dest.write_text(_write_frontmatter(meta, body), encoding="utf-8")
                filepath.unlink()
                print(f"[inbox-router] {title} → 02-Tina-Memory/Ideas/")

            elif classification == "reference":
                _RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
                meta["status"] = "routed"
                dest = _RESOURCES_DIR / new_filename
                dest.write_text(_write_frontmatter(meta, body), encoding="utf-8")
                filepath.unlink()
                print(f"[inbox-router] {title} → 03-Resources/")

            elif classification == "escalate":
                meta["status"] = "needs-review"
                filepath.write_text(_write_frontmatter(meta, body), encoding="utf-8")
                notice = f"Ky, I captured an item I'm not sure how to classify: \"{title}\". It's in your inbox — can you tell me what to do with it?"
                await broadcast({"type": "response", "text": notice})
                await _tts_stream(notice)
                print(f"[inbox-router] {title} → escalated to Ky")

        except Exception as e:
            print(f"[inbox-router] failed on {filepath.name}: {e}")


async def _auto_research_project(slug: str, title: str, content: str):
    """Dispatch Charlie to auto-research a new project from the inbox pipeline."""
    from tina.agents.research import ResearchAgent
    task = (
        f"AUTO-RESEARCH — new project captured from inbox\n\n"
        f"Project: {title}\n\n"
        f"Raw capture:\n{content}\n\n"
        "Research this project and produce a proposed plan document:\n"
        "1. What is this project? Define the scope and goal clearly.\n"
        "2. Research the space — what approaches exist, what tools/frameworks are relevant, who else does this?\n"
        "3. Proposed plan: numbered phases, estimated effort per phase, dependencies, risks.\n"
        "4. Open questions that need Ky's input before starting.\n\n"
        f"Save the plan to vault at 01-Projects/Proposed/{slug}/ as research.md\n"
        "Use vault_write with folder=01-Projects/Proposed/{slug} and filename=research.md\n\n"
        "End with: STATUS: RESEARCH COMPLETE — awaiting Ky's approval to promote."
    ).replace("{slug}", slug)
    await background_runner("research", ResearchAgent, task, None)


async def _run_kaos_monitor():
    """Check KAOS for new support tickets, subscription changes, and waitlist signups."""
    from tools.kaos_tool import _client as _kaos_client, KAOS_SUPABASE_URL
    if not KAOS_SUPABASE_URL:
        return

    _KAOS_STATE_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "kaos_last_check.txt"
    )
    _KAOS_STATE_FILE = os.path.normpath(_KAOS_STATE_FILE)

    # Load last-seen timestamps
    last_ticket_ts = last_waitlist_ts = last_sub_ts = "1970-01-01T00:00:00+00:00"
    if os.path.exists(_KAOS_STATE_FILE):
        try:
            state = _json.loads(open(_KAOS_STATE_FILE).read())
            last_ticket_ts  = state.get("last_ticket",   last_ticket_ts)
            last_waitlist_ts= state.get("last_waitlist", last_waitlist_ts)
            last_sub_ts     = state.get("last_sub",      last_sub_ts)
        except Exception:
            pass

    def _check():
        db = _kaos_client()
        alerts = []

        # New support tickets
        new_tickets = (db.table("support_tickets")
            .select("title, submitted_by_name, submitted_by_email, type, workspace_id")
            .gt("created_at", last_ticket_ts)
            .order("created_at", desc=False)
            .execute().data or [])
        for t in new_tickets:
            who = t.get("submitted_by_name") or t.get("submitted_by_email") or "someone"
            alerts.append(f"New {t.get('type','support')} ticket from {who}: {t.get('title','')}")

        # New waitlist signups
        new_waitlist = (db.table("waitlist")
            .select("email, name")
            .gt("created_at", last_waitlist_ts)
            .order("created_at", desc=False)
            .execute().data or [])
        if new_waitlist:
            names = ", ".join(w.get("name") or w.get("email","?") for w in new_waitlist[:3])
            alerts.append(f"{len(new_waitlist)} new waitlist signup{'s' if len(new_waitlist)>1 else ''}: {names}")

        # Subscription changes
        new_subs = (db.table("workspace_subscriptions")
            .select("status, workspace_id, workspaces(name)")
            .gt("updated_at", last_sub_ts)
            .order("updated_at", desc=False)
            .execute().data or [])
        for s in new_subs:
            ws_name = (s.get("workspaces") or {}).get("name", "a workspace")
            status  = s.get("status", "?")
            if status == "active":
                alerts.append(f"KAOS subscription activated: {ws_name} is now paying.")
            elif status in ("cancelled", "canceled"):
                alerts.append(f"KAOS cancellation: {ws_name} has cancelled.")
            elif status == "trialing":
                alerts.append(f"KAOS trial started: {ws_name} is now trialing.")

        # New Sentry errors
        last_sentry_ts = state.get("last_sentry", "1970-01-01T00:00:00") if os.path.exists(_KAOS_STATE_FILE) else "1970-01-01T00:00:00"
        from tools.kaos_tool import sentry_new_issues_since
        new_errors = sentry_new_issues_since(last_sentry_ts)
        fatal = [e for e in new_errors if e.get("level") in ("fatal", "error")]
        if fatal:
            titles = "; ".join(e.get("title", "?") for e in fatal[:3])
            alerts.append(f"{len(fatal)} new KAOS error{'s' if len(fatal)>1 else ''} in Sentry: {titles}")

        # Current platform totals for live tile
        try:
            total_users   = (db.table("workspaces").select("id", count="exact").execute().count or 0)
            open_tickets  = (db.table("support_tickets").select("id", count="exact").eq("status", "open").execute().count or 0)
            active_subs   = (db.table("workspace_subscriptions").select("workspace_id", count="exact").eq("status", "active").execute().count or 0)
            trial_subs    = (db.table("workspace_subscriptions").select("workspace_id", count="exact").eq("status", "trialing").execute().count or 0)
        except Exception:
            total_users = open_tickets = active_subs = trial_subs = None

        # Save updated timestamps
        new_state = {
            "last_ticket":   (new_tickets[-1]["created_at"]  if new_tickets  else last_ticket_ts),
            "last_waitlist": (new_waitlist[-1]["created_at"] if new_waitlist else last_waitlist_ts),
            "last_sub":      (new_subs[-1]["updated_at"]     if new_subs     else last_sub_ts),
            "last_sentry":   (new_errors[-1]["firstSeen"]    if new_errors   else last_sentry_ts),
        }
        with open(_KAOS_STATE_FILE, "w") as f:
            _json.dump(new_state, f)

        totals = {"users": total_users, "tickets": open_tickets, "active_subs": active_subs, "trial_subs": trial_subs}
        return alerts, totals

    try:
        alerts, kaos_totals = await asyncio.to_thread(_check)
        import uuid as _uuid, time as _time
        for alert in alerts:
            lower = alert.lower()
            color = (
                "#ef4444" if any(w in lower for w in ("error", "fatal", "sentry", "cancelled", "canceled", "dispute"))
                else "#4ade80" if any(w in lower for w in ("activated", "paying", "trial started"))
                else "#60a5fa" if "waitlist" in lower
                else "#f59e0b"
            )
            title = (
                "KAOS ERROR"    if any(w in lower for w in ("error", "fatal", "sentry"))
                else "KAOS REVENUE" if any(w in lower for w in ("activated", "paying"))
                else "CANCELLATION" if any(w in lower for w in ("cancelled", "canceled"))
                else "KAOS"
            )
            await broadcast({
                "type": "featured_panel", "id": str(_uuid.uuid4()),
                "title": title, "content": alert[:380],
                "color": color, "ttl": 90000, "ts": int(_time.time() * 1000),
            })
            print(f"[kaos-monitor] {alert}")
            await broadcast({"type": "response", "text": alert})
            await _tts_stream(alert)
            await _slack_post(f":warning: *KAOS* — {alert}")
        # Always broadcast live tile with current totals
        import time as _time2
        await broadcast({"type": "kaos_live", **kaos_totals, "ts": int(_time2.time() * 1000)})
    except Exception as e:
        print(f"[kaos-monitor] error: {e}")


async def _schedule_kaos_monitor():
    """Check KAOS every 15 minutes for new tickets, signups, and subscription changes."""
    await asyncio.sleep(180)  # Let the system settle
    while True:
        if not _gaming_mode:
            try:
                await _run_kaos_monitor()
            except Exception as e:
                print(f"[kaos-monitor] scheduler error: {e}")
        await asyncio.sleep(900)  # 15 minutes


async def _run_stripe_monitor():
    """Check Stripe for failed charges, new subscriptions, cancellations, and disputes."""
    from config import STRIPE_SECRET_KEY
    if not STRIPE_SECRET_KEY:
        return

    _STATE_FILE = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "stripe_last_check.txt"
    ))

    import time as _time
    now_ts  = int(_time.time())
    last_ts = now_ts - 1800  # default: last 30 minutes
    if os.path.exists(_STATE_FILE):
        try:
            last_ts = int(open(_STATE_FILE).read().strip())
        except Exception:
            pass

    def _check():
        """Check for new Stripe events using stripe_tool's HTTP client — no SDK needed."""
        import httpx as _httpx
        alerts = []
        if not STRIPE_SECRET_KEY:
            return alerts
        try:
            resp = _httpx.get(
                "https://api.stripe.com/v1/events",
                headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
                params={
                    "created[gt]": last_ts,
                    "types[]": [
                        "charge.failed",
                        "invoice.payment_failed",
                        "customer.subscription.created",
                        "customer.subscription.deleted",
                        "charge.dispute.created",
                    ],
                    "limit": 25,
                },
                timeout=20,
            )
            resp.raise_for_status()
            events = resp.json().get("data", [])
        except Exception as e:
            print(f"[stripe-monitor] API error: {e}")
            return alerts

        for event in events:
            obj   = event.get("data", {}).get("object", {})
            etype = event.get("type", "")

            if etype == "charge.failed":
                amount = obj.get("amount", 0) / 100
                email  = (obj.get("billing_details") or {}).get("email") or "unknown"
                alerts.append(("CHARGE FAILED", f"${amount:.2f} charge failed\n{email}", "#ef4444"))

            elif etype == "invoice.payment_failed":
                amount = obj.get("amount_due", 0) / 100
                alerts.append(("PAYMENT FAILED", f"Invoice ${amount:.2f} payment failed", "#ef4444"))

            elif etype == "customer.subscription.created":
                items  = (obj.get("items") or {}).get("data") or [{}]
                price  = (items[0].get("price") or {})
                plan   = price.get("nickname") or price.get("id") or "plan"
                amount = price.get("unit_amount", 0) / 100
                alerts.append(("NEW SUBSCRIBER", f"New subscription: {plan}\n${amount:.2f}/mo", "#4ade80"))

            elif etype == "customer.subscription.deleted":
                items = (obj.get("items") or {}).get("data") or [{}]
                price = (items[0].get("price") or {})
                plan  = price.get("nickname") or price.get("id") or "plan"
                alerts.append(("CANCELLATION", f"Subscription cancelled: {plan}", "#f59e0b"))

            elif etype == "charge.dispute.created":
                amount = obj.get("amount", 0) / 100
                alerts.append(("DISPUTE", f"Chargeback dispute opened\n${amount:.2f}", "#ef4444"))

        return alerts

    def _get_mrr():
        """Fetch active subscription MRR via direct HTTP — no SDK needed."""
        import httpx as _httpx
        if not STRIPE_SECRET_KEY:
            return 0.0, 0
        mrr, count, has_more, starting_after = 0.0, 0, True, None
        while has_more:
            params = {"status": "active", "limit": 100, "expand[]": "data.items.data.price"}
            if starting_after:
                params["starting_after"] = starting_after
            resp = _httpx.get(
                "https://api.stripe.com/v1/subscriptions",
                headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
                params=params, timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            for s in data.get("data", []):
                count += 1
                for item in (s.get("items") or {}).get("data", []):
                    price    = item.get("price") or {}
                    amt      = price.get("unit_amount", 0) or 0
                    qty      = item.get("quantity", 1) or 1
                    interval = (price.get("recurring") or {}).get("interval", "month")
                    mrr += (amt * qty) / 12 / 100 if interval == "year" else (amt * qty) / 100
            has_more = data.get("has_more", False)
            if has_more and data.get("data"):
                starting_after = data["data"][-1]["id"]
        return round(mrr, 2), count

    try:
        alerts = await asyncio.to_thread(_check)
        import uuid as _uuid, time as _time2
        for title, content, color in alerts:
            print(f"[stripe-monitor] {title}: {content[:80]}")
            await broadcast({
                "type": "featured_panel", "id": str(_uuid.uuid4()),
                "title": title, "content": content,
                "color": color, "ttl": 120000, "ts": int(_time2.time() * 1000),
            })
            if color == "#ef4444":
                msg = f"Stripe alert: {content.replace(chr(10), '. ')}"
                await broadcast({"type": "response", "text": msg})
                await _tts_stream(msg)
            await _slack_post(f":credit_card: *STRIPE* — {content.replace(chr(10), ' — ')}")
        with open(_STATE_FILE, "w") as f:
            f.write(str(now_ts))
        try:
            mrr_val, sub_count = await asyncio.to_thread(_get_mrr)
            import time as _time3
            await broadcast({"type": "stripe_live", "mrr": mrr_val, "active_subs": sub_count, "ts": int(_time3.time() * 1000)})
        except Exception as mrr_e:
            print(f"[stripe-monitor] MRR tile error: {mrr_e}")
    except Exception as e:
        print(f"[stripe-monitor] error: {e}")


async def _schedule_stripe_monitor():
    """Check Stripe every 30 minutes for payment events."""
    await asyncio.sleep(240)
    while True:
        if not _gaming_mode:
            try:
                await _run_stripe_monitor()
            except Exception as e:
                print(f"[stripe-monitor] scheduler error: {e}")
        await asyncio.sleep(1800)  # 30 minutes


async def _run_pattern_scan():
    """Dispatch Connor to analyse KAOS support tickets for recurring patterns."""
    from tina.agents.data import DataAgent
    from datetime import date

    today_str = date.today().strftime("%d %B %Y")
    print(f"[pattern-scan] starting for {today_str}")

    task = (
        f"FEATURE REQUEST PATTERN SCAN — {today_str}\n\n"
        "Analyse KAOS support tickets to identify recurring patterns and product signals.\n\n"
        "STEPS:\n"
        "1. Call kaos_support_tickets with no status filter and limit=100 to get all recent tickets\n"
        "2. Call kaos_overview for total context (user count, open ticket count)\n"
        "3. Read through ALL tickets and group them by recurring theme — "
        "look for tickets describing the same problem, requesting the same feature, "
        "or expressing the same confusion\n"
        "4. For each theme, count occurrences and note example ticket descriptions\n\n"
        "CLASSIFICATION:\n"
        "- HIGH signal: 5+ tickets on the same theme — clear product gap, action required\n"
        "- MEDIUM signal: 3-4 tickets — emerging pattern worth watching\n"
        "- EMERGING: 2 tickets — log it but no escalation needed\n"
        "- Ignore one-off tickets with no match\n\n"
        "OUTPUT:\n"
        "Write a pattern report to vault at 02-Tina-Memory/Agents/Connor/ "
        f"with filename {date.today().isoformat()}-kaos-pattern-scan.md\n"
        "Include for each pattern: theme name, signal level, ticket count, example descriptions, suggested action\n\n"
        "Your completion report must be spoken-friendly (2-3 sentences Tina can read aloud): "
        "how many patterns found, the highest priority one, and whether Ky needs to act on anything this week."
    )

    await background_runner("data", DataAgent, task, None)
    print("[pattern-scan] Connor dispatched")


async def _schedule_pattern_scan():
    """Run the feature request pattern scan every Sunday evening."""
    PATTERN_SCAN_FILE = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "pattern_scan_date.txt"
    ))

    while True:
        await asyncio.sleep(60)
        if _gaming_mode:
            continue
        now = datetime.now()

        # Fire on Sunday (weekday 6) at or after 18:00
        if now.weekday() != 6 or now.hour < 18:
            continue

        week_key = now.strftime("%Y-W%W")
        try:
            if os.path.exists(PATTERN_SCAN_FILE):
                if open(PATTERN_SCAN_FILE).read().strip() == week_key:
                    await asyncio.sleep(3600)
                    continue
        except Exception:
            pass

        try:
            await _run_pattern_scan()
            os.makedirs(os.path.dirname(PATTERN_SCAN_FILE), exist_ok=True)
            with open(PATTERN_SCAN_FILE, "w") as f:
                f.write(week_key)
        except Exception as e:
            print(f"[pattern-scan] failed: {e}")

        await asyncio.sleep(3600)


async def _schedule_inbox_pipeline():
    """Classify and route inbox items every 15 minutes."""
    await asyncio.sleep(120)  # Let the system settle after startup
    while True:
        if not _gaming_mode:
            try:
                await _run_inbox_classifier()
                await _run_inbox_router()
            except Exception as e:
                print(f"[inbox-pipeline] error: {e}")
        await asyncio.sleep(900)  # 15 minutes


def _promote_project(project_name: str) -> str:
    """Move a proposed project to an active project folder. Called by tool and REST endpoint."""
    if not _PROPOSED_DIR.exists():
        return f"No proposed projects found — {_PROPOSED_DIR} does not exist."

    name_lower = project_name.lower()
    name_words = set(name_lower.split())

    # Find best match in Proposed/
    candidates = [d for d in _PROPOSED_DIR.iterdir() if d.is_dir()]
    if not candidates:
        return "No proposed projects found in 01-Projects/Proposed/."

    match = None
    for d in candidates:
        folder_lower = d.name.lower()
        folder_words = set(folder_lower.replace("-", " ").split())
        if name_lower in folder_lower or folder_words & name_words:
            match = d
            break

    if not match:
        names = ", ".join(d.name for d in candidates)
        return f"No proposed project matching '{project_name}' found. Available: {names}"

    # Move to active projects
    active_dir = _VAULT_ROOT / "01-Projects" / match.name
    if active_dir.exists():
        return f"Project '{match.name}' already exists as an active project at 01-Projects/{match.name}/."

    shutil.copytree(str(match), str(active_dir))

    # Update status in capture.md if it exists
    capture_file = active_dir / "capture.md"
    if capture_file.exists():
        raw = capture_file.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        meta["status"] = "active"
        capture_file.write_text(_write_frontmatter(meta, body), encoding="utf-8")

    shutil.rmtree(str(match))

    return (
        f"Project '{match.name}' has been promoted to active status at 01-Projects/{match.name}/. "
        "It's ready for execution."
    )


async def _post_restart_cleanup():
    """Clean up the post_restart sentinel left by system_tool.restart_backend."""
    from config import BASE_DIR
    sentinel = os.path.join(BASE_DIR, "data", "post_restart.json")
    if os.path.exists(sentinel):
        try:
            os.remove(sentinel)
            print("[lifespan] cleared post_restart sentinel")
        except Exception:
            pass


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
    global _gaming_mode
    _gaming_mode = bool(_load_prefs().get("gaming_mode", False))
    if _gaming_mode:
        print("[gaming-mode] restored ENABLED from prefs — schedulers will stay paused until disabled")

    asyncio.create_task(_schedule_nightly_reindex())
    asyncio.create_task(_run_startup_briefing())
    asyncio.create_task(_post_restart_cleanup())
    asyncio.create_task(_drain_preview_queue())
    asyncio.create_task(_resume_pending_tasks())
    asyncio.create_task(_schedule_weekly_briefing())
    asyncio.create_task(_schedule_email_triage())
    asyncio.create_task(_schedule_inbox_pipeline())
    asyncio.create_task(_schedule_kaos_monitor())
    asyncio.create_task(_schedule_stripe_monitor())
    asyncio.create_task(_schedule_pattern_scan())
    asyncio.create_task(_start_slack_listener())

    # Wake-word detector — disabled by default; set WAKE_WORD_ENABLED=true in .env to enable.
    # Holding a WASAPI capture session open continuously triggers audio driver AEC globally,
    # making Spotify/YouTube sound robotic. Only enable if your hardware handles it cleanly.
    if WAKE_WORD_ENABLED:
        try:
            from tina.wake_word import start as _ww_start
            _ww_loop = asyncio.get_running_loop()

            async def _on_wake_word(status: str, text: str):
                if status == "triggered":
                    await broadcast({"type": "wake_word_detected"})
                elif status == "ready":
                    await broadcast({"type": "wake_word_ready"})

            _ww_start(_ww_loop, _on_wake_word)
        except Exception as e:
            print(f"[wake-word] could not start: {e}")
    else:
        print("[wake-word] disabled (WAKE_WORD_ENABLED=false) — use spacebar to talk")
        # Tell frontend not to start Web Speech API either
        asyncio.get_running_loop().call_later(
            2.0, lambda: asyncio.ensure_future(broadcast({"type": "wake_word_disabled"}))
        )

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

# Approvals/questions pending from background agents — answered via voice or text input
_pending_approvals: dict[str, dict] = {}  # agent_key → {queue, display}

# Serialises all TTS output — prevents two agents speaking simultaneously
_tts_lock = asyncio.Lock()

_APPROVAL_WORDS = frozenset([
    "yes", "approved", "approve", "go ahead", "go for it",
    "good to go", "proceed", "looks good", "do it", "confirmed",
    "yeah", "yep", "ok", "okay", "sure", "fine", "sounds good",
    "ship it", "let's go", "lets go", "absolutely", "correct",
])

def _is_approval(text: str) -> bool:
    lower = text.lower().strip().rstrip(".")
    return lower in _APPROVAL_WORDS or any(kw in lower for kw in _APPROVAL_WORDS)


async def broadcast(data: dict):
    # Gaming mode: hold back popup cards / proactive alerts so nothing pops over a game.
    if _gaming_mode and data.get("type") == "featured_panel":
        return
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


async def _slack_post(text: str) -> None:
    """Post a message to the main Slack channel."""
    if not SLACK_TINA_BOT_TOKEN or not SLACK_CHANNEL:
        return
    try:
        from slack_sdk.web.async_client import AsyncWebClient
        client = AsyncWebClient(token=SLACK_TINA_BOT_TOKEN)
        await client.chat_postMessage(channel=SLACK_CHANNEL, text=text)
    except Exception as e:
        print(f"[slack] post failed: {e}")


async def _handle_slack_message(text: str) -> None:
    """Process a message from Ky via Slack — routes through TINA, reply posted back to Slack."""
    await broadcast({"type": "heard", "text": f"[SLACK] {text}"})
    await broadcast({"type": "state", "state": "thinking"})
    async with _agent_lock:
        reply = await agent.chat(text, background=True)
    print(f"\n[TINA→SLACK] {reply}\n")
    await broadcast({"type": "response", "text": reply})
    await _slack_post(reply)
    asyncio.create_task(_write_memory(text, reply, list(agent.history)))


async def _start_slack_listener() -> None:
    """Start the Slack Socket Mode listener so Ky can talk to TINA from Slack."""
    if not SLACK_APP_TOKEN or not SLACK_TINA_BOT_TOKEN:
        print("[slack] APP_TOKEN or BOT_TOKEN not configured — skipping listener")
        return
    try:
        from slack_sdk.socket_mode.aiohttp import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.web.async_client import AsyncWebClient
    except ImportError:
        print("[slack] slack_sdk aiohttp support not installed — run: pip install slack_sdk[aiohttp]")
        return

    web_client = AsyncWebClient(token=SLACK_TINA_BOT_TOKEN)
    sm_client  = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

    async def handle_event(client, req):
        if req.type == "events_api":
            await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
            event = req.payload.get("event", {})
            if (
                event.get("type") == "message"
                and not event.get("bot_id")
                and not event.get("subtype")
                and (not SLACK_KY_USER_ID or event.get("user") == SLACK_KY_USER_ID)
            ):
                text = event.get("text", "").strip()
                if text:
                    asyncio.create_task(_handle_slack_message(text))

    sm_client.socket_mode_request_listeners.append(handle_event)
    await sm_client.connect()
    print("[slack] Socket Mode listener connected")
    await asyncio.sleep(float("inf"))


# ── Background agent runner ───────────────────────────────────────────────────

async def _get_tina_answer(question: str) -> str:
    """Answer a clarifying question from an agent using Tina's current conversation context."""
    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        # Sanitize history before use — a corrupted turn causes a 400 that
        # silently returns the fallback, leaving the agent with no real answer.
        clean_history = TinaAgent._sanitize_history(list(agent.history))
        messages = clean_history + [{
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

    # Suspiciously short result — only fail if truly empty or near-empty.
    # A short but valid completion summary (e.g. "Done. Files at ...") must pass.
    if len(result.strip()) < 20 and len(task) > 300:
        return False, "Result is too short for this task — likely incomplete or crashed early."

    # Haiku self-assessment as the final check
    # Use the tail of the result — that's where conclusions and completion status live.
    # Include a short head for context, then the final 700 chars where the outcome is stated.
    try:
        head = result[:200]
        tail = result[-700:] if len(result) > 900 else ""
        log_excerpt = head + ("\n…\n" + tail if tail else "")
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=(
                "You are a task-completion auditor for an AI assistant system. "
                "You will be given a task brief and an excerpt from the agent's output log (start + end). "
                "Your job is to assess whether the log shows the task was completed successfully.\n\n"
                "Focus on the END of the log — that is where the final outcome is stated. "
                "Look for: explicit success confirmation, files/records confirmed written, no unresolved errors.\n\n"
                'Respond with JSON only: {"completed": true/false, "message": "1-2 sentence summary for Tina"}\n\n'
                "If completed: name exactly what the log confirms was done (file paths, recipients, outcomes).\n"
                "If failed or partial: state what the log shows went wrong.\n"
                "Be strict — 'I will do X' is not the same as 'X was done'. Do not infer completion from intent. No preamble."
            ),
            messages=[{"role": "user", "content": f"Task brief: {task[:400]}\n\nAgent output log (start + end):\n{log_excerpt}"}],
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
    await asyncio.sleep(4)
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
            print(f"[resume] Resuming interrupted {agent_key} task: {task[:60]}...")
            asyncio.create_task(_run_agent_background(agent_key, cls, task, None,
                                                      task_id=task_id, retried=True))
        except Exception as e:
            print(f"[resume] Failed to resume {fname}: {e}")


async def background_runner(agent_key: str, cls, task: str, on_tool, then_spec: dict | None = None):
    """Called by TinaAgent._dispatch — persists the task then launches it."""
    task_id = str(uuid.uuid4())
    _save_pending_task(task_id, agent_key, task)
    asyncio.create_task(_run_agent_background(agent_key, cls, task, on_tool, task_id=task_id, then_spec=then_spec))


async def _run_agent_background(agent_key: str, cls, task: str, on_tool,
                                task_id: str = None, retried: bool = False,
                                then_spec: dict | None = None):
    """Runs a specialist agent independently. Results delivered via dashboard + TTS."""
    from tina.agent_state import start_task, record_tool, end_task, summarize_input

    meta    = _AGENT_META.get(agent_key, {"display": agent_key, "color": "#8B5CF6", "glow": "#A78BFA"})
    display = meta["display"]

    async def tracking_on_tool(name: str, inputs: dict = None):
        record_tool(agent_key, name, summarize_input(name, inputs or {}))
        if on_tool:
            await on_tool(name, inputs)

    async def tracking_on_tool_result(name: str, inputs: dict, result):
        event = _make_tool_result_event(name, result)
        if event:
            await broadcast(event)

    async def question_handler(question: str) -> str:
        """Agent has a clarifying question — auto-answer or escalate to Ky via TTS."""
        escalate, tina_answer = await asyncio.gather(
            _should_escalate_to_kai(question),
            _get_tina_answer(question),
        )
        if not escalate:
            asyncio.create_task(_tts_stream(f"{display} has a question. {tina_answer}"))
            await broadcast({"type": "response", "text": f"{display}: {question}\n\nTina: {tina_answer}"})
            return tina_answer
        spoken = f"{display} needs your input. {question} Tina suggests: {tina_answer}"
        await broadcast({"type": "response", "text": spoken})
        q: asyncio.Queue = asyncio.Queue()
        _pending_approvals[agent_key] = {"queue": q, "display": display}
        asyncio.create_task(_tts_stream(spoken))
        try:
            return await asyncio.wait_for(q.get(), timeout=14400)
        except asyncio.TimeoutError:
            return tina_answer
        finally:
            _pending_approvals.pop(agent_key, None)

    async def plan_handler(plan: str) -> str:
        """Agent has a plan — broadcast it and wait for Ky's voice approval."""
        spoken = f"{display} has a plan ready and is waiting for your approval. Say approved when ready."
        await broadcast({"type": "agent_plan", "agent": display, "key": agent_key, "plan": plan})
        await broadcast({"type": "response", "text": spoken})
        q: asyncio.Queue = asyncio.Queue()
        _pending_approvals[agent_key] = {"queue": q, "display": display}
        asyncio.create_task(_tts_stream(spoken))
        try:
            return await asyncio.wait_for(q.get(), timeout=86400)
        except asyncio.TimeoutError:
            return "approved"
        finally:
            _pending_approvals.pop(agent_key, None)

    try:
        start_task(agent_key, task)
        print(f"[{display}] background task started: {task[:80]}...")

        async def _broadcast_start():
            if retried:
                await asyncio.sleep(3)
            await broadcast({
                "type":  "agent_background_start",
                "agent": meta["display"],
                "key":   agent_key,
                "color": meta.get("color", "#8B5CF6"),
                "glow":  meta.get("glow",  "#A78BFA"),
                "task":  task[:120],
            })
        asyncio.create_task(_broadcast_start())

        specialist = cls()
        result     = await specialist.run(task, on_tool=tracking_on_tool, on_tool_result=tracking_on_tool_result, question_handler=question_handler, plan_handler=plan_handler)

        print(f"[{display}] background task complete ({len(result)} chars)")

        completed, verify_msg = await _agent_verify_response(display, task, result)

        if completed:
            verbal_summary = await _tina_verbal_summary(display, result)
            summary = result[:300] + "…" if len(result) > 300 else result
            await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": summary})
            await broadcast({"type": "response", "text": verbal_summary})
            asyncio.create_task(_tts_stream(verbal_summary))
            asyncio.create_task(_slack_post(f"*{display}* — {verbal_summary}"))
            # Agent handoff — auto-dispatch follow-on agent if one was specified
            if then_spec:
                _then_key  = then_spec.get("agent", "")
                _then_cls  = then_spec.get("cls")
                _then_task = then_spec.get("task", "").replace("{result}", verbal_summary)
                if _then_key and _then_cls and _then_task:
                    notice = f"{display} finished. Handing off to {_then_key.capitalize()} now."
                    await broadcast({"type": "response", "text": notice})
                    asyncio.create_task(_tts_stream(notice))
                    asyncio.create_task(_run_agent_background(_then_key, _then_cls, _then_task, None))
                    print(f"[handoff] {agent_key} → {_then_key}")

            # Proactive popup for email triage — surface urgent items immediately
            if agent_key == "email":
                import uuid as _uuid, time as _time
                _lower = result.lower()
                _urgent = "urgent" in _lower
                _title  = "URGENT EMAIL" if _urgent else "EMAIL TRIAGE"
                _color  = "#ef4444"    if _urgent else "#60a5fa"
                _ttl    = 120000       if _urgent else 60000
                await broadcast({
                    "type": "featured_panel", "id": str(_uuid.uuid4()),
                    "title": _title, "content": verbal_summary[:380],
                    "color": _color, "ttl": _ttl, "ts": int(_time.time() * 1000),
                })
        else:
            issue_summary = f"{display} ran into an issue: {verify_msg}"
            await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": f"Issue: {verify_msg}"})
            await broadcast({"type": "response", "text": issue_summary})
            asyncio.create_task(_tts_stream(issue_summary))
            asyncio.create_task(_slack_post(f"*{display}* — {issue_summary}"))
            asyncio.create_task(_write_error_memory(agent_key, task, verify_msg))

    except asyncio.CancelledError:
        print(f"[{display}] background task cancelled (server restart) — will resume on next start")
        raise
    except Exception as e:
        print(f"[{display}] background task error: {e}")
        from tina.agent_state import _progress
        completed_steps = _progress.get(agent_key, {}).get("history", [])
        err_summary = f"Error after {len(completed_steps)} steps: {e}"
        await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": err_summary})
        await broadcast({"type": "response", "text": f"{display} hit an error: {e}"})
        asyncio.create_task(_tts_stream(f"{display} hit an error. Check the logs for details."))
    finally:
        end_task(agent_key)
        if task_id and not asyncio.current_task().cancelled():
            _clear_pending_task(task_id)


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
            json={
                "text":     text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability":        0.45,
                    "similarity_boost": 0.80,
                    "style":            0.10,
                    "use_speaker_boost": True,
                },
            },
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
    """Send reply to ElevenLabs as one call. Serialised via _tts_lock — no simultaneous playback."""
    # Gaming mode: stay silent. The text was already broadcast to the dashboard.
    if _gaming_mode:
        return
    async with _tts_lock:
        # Pause wake-word detector so TINA's voice doesn't re-trigger herself
        try:
            from tina.wake_word import pause as _ww_pause, resume as _ww_resume
            _ww_pause()
        except Exception:
            _ww_pause = _ww_resume = None

        await broadcast({"type": "state", "state": "speaking"})

        if ELEVENLABS_API_KEY:
            audio = await synthesise(reply.strip())
            if audio:
                await broadcast({
                    "type":   "audio_chunk",
                    "format": ELEVENLABS_FORMAT,
                    "index":  0,
                    "data":   base64.b64encode(audio).decode(),
                })
            else:
                print("[TTS] ElevenLabs returned nothing — falling back to pyttsx3")
                await _pyttsx3_speak(reply)
        else:
            await _pyttsx3_speak(reply)

        await broadcast({"type": "audio_end"})

        # Resume wake-word detector after a short buffer (audio may still be playing)
        try:
            await asyncio.sleep(1.5)
            from tina.wake_word import resume as _ww_resume
            _ww_resume()
        except Exception:
            pass


async def _handle_message(text: str):
    """Shared logic for text input from both voice (STT) and typed messages."""
    # Internal system signals from the dashboard — inject into Tina's history for future
    # context but do NOT generate a spoken response (the agent already spoke via verbal_summary).
    if text.startswith('[SYSTEM:'):
        agent.history.append({"role": "user", "content": text})
        return

    # Voice/text control: gaming mode on/off/toggle. Intercept before anything else so
    # it works even while an agent is awaiting approval. "gaming mode" alone toggles.
    _low = text.lower()
    if "gaming mode" in _low:
        if any(w in _low for w in ("off", "disable", "stop", "end", "deactivate", "exit", "done")):
            await _set_gaming_mode(False)
        elif any(w in _low for w in ("on", "enable", "start", "activate", "begin", "engage")):
            await _set_gaming_mode(True)
        else:
            await _set_gaming_mode(not _gaming_mode)
        await broadcast({"type": "state", "state": "listening"})
        return

    # Check if an agent is waiting for Ky's approval and this message is one
    if _pending_approvals:
        if _is_approval(text):
            names = []
            for ak, info in list(_pending_approvals.items()):
                await info["queue"].put(text)
                names.append(info["display"])
            reply = f"Approved — passing that to {' and '.join(names)} now."
            await broadcast({"type": "state", "state": "responding"})
            await broadcast({"type": "response", "text": reply})
            await _tts_stream(reply)
            await broadcast({"type": "state", "state": "listening"})
            return
        # Not an approval word — could be feedback/redirect, route to the pending agent
        if len(_pending_approvals) == 1:
            ak, info = next(iter(_pending_approvals.items()))
            await info["queue"].put(text)
            reply = f"Got it — passing that feedback to {info['display']}."
            await broadcast({"type": "state", "state": "responding"})
            await broadcast({"type": "response", "text": reply})
            await _tts_stream(reply)
            await broadcast({"type": "state", "state": "listening"})
            return

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


@app.post("/api/trigger-weekly-briefing")
async def trigger_weekly_briefing():
    """Manually trigger the weekly business briefing."""
    asyncio.create_task(_run_weekly_briefing())
    return {"ok": True, "message": "Weekly briefing started — Connor, Wade, and Tristan dispatched."}


@app.post("/api/trigger-email-triage")
async def trigger_email_triage():
    """Manually trigger an autonomous email triage."""
    asyncio.create_task(_run_email_triage())
    return {"ok": True, "message": "Email triage started — Tristan is on it."}


@app.post("/api/trigger-inbox-pipeline")
async def trigger_inbox_pipeline():
    """Manually run the classify + route pipeline right now."""
    asyncio.create_task(_run_inbox_classifier())
    asyncio.create_task(_run_inbox_router())
    return {"ok": True, "message": "Inbox pipeline running — classifier then router."}


@app.post("/api/trigger-pattern-scan")
async def trigger_pattern_scan():
    """Manually run the KAOS feature request pattern scan."""
    asyncio.create_task(_run_pattern_scan())
    return {"ok": True, "message": "Pattern scan started — Connor is analysing support tickets."}


@app.post("/api/promote/{project_name}")
async def promote_project_endpoint(project_name: str):
    """Promote a proposed project to active status and dispatch Morgan to execute it."""
    result = await asyncio.to_thread(_promote_project, project_name)
    if "active status" in result:
        from tina.agents.pm import ProjectManagerAgent
        slug = re.sub(r"[^\w\s-]", "", project_name.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:60]
        morgan_task = (
            f"EXECUTE PROJECT: {project_name}\n\n"
            f"{result}\n\n"
            f"The active project folder is 01-Projects/{slug}/ (or the closest match). "
            "Read capture.md and research.md from that folder, build an execution plan, "
            "and coordinate the right agents to complete the project."
        )
        asyncio.create_task(background_runner("pm", ProjectManagerAgent, morgan_task, None))
    return {"ok": True, "message": result}


@app.get("/api/status")
async def get_status():
    from config import DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, GITHUB_TOKEN, TAVILY_API_KEY, OPENWEATHER_API_KEY, SLACK_TINA_BOT_TOKEN
    return {
        "deepgram":    bool(DEEPGRAM_API_KEY),
        "elevenlabs":  bool(ELEVENLABS_API_KEY),
        "github":      bool(GITHUB_TOKEN),
        "tavily":      bool(TAVILY_API_KEY),
        "weather":     bool(OPENWEATHER_API_KEY),
        "slack":       bool(SLACK_TINA_BOT_TOKEN),
    }


@app.post("/api/broadcast-panel")
async def broadcast_panel(payload: dict):
    """Push a featured data panel to all connected dashboard clients."""
    await broadcast({"type": "featured_panel", **payload})
    return {"ok": True}


@app.post("/api/show-email-drafts")
async def show_email_drafts():
    """Extract pending drafts from latest triage report and broadcast to dashboard."""
    import glob as _glob
    from config import VAULT_DIR

    tristan_dir = os.path.join(VAULT_DIR, "02-Tina-Memory", "Agents", "Tristan")
    if not os.path.isdir(tristan_dir):
        return {"error": "No triage reports found"}

    triage_files = sorted(_glob.glob(os.path.join(tristan_dir, "*-triage.md")))
    if not triage_files:
        return {"error": "No triage reports found"}

    content = open(triage_files[-1], encoding="utf-8").read()
    source  = os.path.basename(triage_files[-1])

    # Use Haiku to extract structured draft data from the markdown
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=(
            "Extract email drafts from this triage report. "
            "Return ONLY a valid JSON array — no markdown fences, no explanation. "
            'Each item must have: {"priority":"URGENT"|"NORMAL","account":"personal"|"business_gmail"|"business_outlook",'
            '"from":"sender name and email","subject":"subject line","body":"the full drafted reply text"}. '
            "Include ONLY NORMAL and URGENT emails. If none exist, return []."
        ),
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in resp.content if hasattr(b, "text")), "[]").strip()
    # Strip accidental markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        drafts = _json.loads(text)
    except Exception:
        drafts = []

    await broadcast({"type": "email_drafts", "drafts": drafts, "source": source})
    return {"drafts": drafts, "source": source}


@app.post("/api/email-send")
async def send_email_draft(payload: dict):
    """Send a drafted email reply directly via email_tool."""
    from tools.email_tool import handle as _email_handle
    account = payload.get("account", "personal")
    to      = payload.get("to", "")
    subject = payload.get("subject", "")
    body    = payload.get("body", "")
    if not to or not body:
        return {"error": "Missing recipient or body"}
    result = await asyncio.to_thread(
        _email_handle, "email_send",
        {"account": account, "to": to, "subject": subject, "body": body},
    )
    return {"result": result}


@app.get("/api/pipeline")
async def get_pipeline():
    """Return project pipeline state — inbox, proposed, and active projects."""
    from pathlib import Path
    from config import VAULT_DIR

    inbox_dir    = Path(VAULT_DIR) / "00-Inbox"
    proposed_dir = Path(VAULT_DIR) / "01-Projects" / "Proposed"
    active_dir   = Path(VAULT_DIR) / "01-Projects"

    def _title_from_md(path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.index("---", 3)
                for line in text[3:end].splitlines():
                    if line.lower().startswith("title:"):
                        return line.split(":", 1)[1].strip().strip("\"'")
        except Exception:
            pass
        return ""

    def _dir_title(d: Path) -> str:
        for md in ("capture.md", "README.md", "index.md"):
            t = _title_from_md(d / md)
            if t:
                return t
        return d.name.replace("-", " ").replace("_", " ").title()

    inbox = []
    if inbox_dir.exists():
        for f in sorted(inbox_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                text = f.read_text(encoding="utf-8")
                status = "new"
                if text.startswith("---"):
                    end = text.index("---", 3)
                    for line in text[3:end].splitlines():
                        if line.lower().startswith("status:"):
                            status = line.split(":", 1)[1].strip()
            except Exception:
                status = "new"
            inbox.append({"filename": f.name, "status": status})

    proposed = []
    if proposed_dir.exists():
        for d in sorted(proposed_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir():
                proposed.append({"slug": d.name, "title": _dir_title(d)})

    active = []
    if active_dir.exists():
        for d in sorted(active_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if d.is_dir() and d.name != "Proposed":
                active.append({"slug": d.name, "title": _dir_title(d)})

    return {"inbox": inbox, "proposed": proposed, "active": active}


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
        speech  = f"Diagnostic complete. I found {summary} — {names}. I'll go through the details now."
        await broadcast({"type": "response", "text": speech})
        asyncio.create_task(_tts_stream(speech))
        asyncio.create_task(_diag_review(issues))
    else:
        speech = "All systems healthy. Everything passed."
        await broadcast({"type": "response", "text": speech})
        asyncio.create_task(_tts_stream(speech))


async def _diag_review(issues: list[tuple[str, str, str]]):
    """Review diagnostic issues and give Ky a plain-spoken summary with fix actions."""
    lines = "\n".join(f"{status.upper()}: {label} — {detail}" for label, status, detail in issues)
    prompt = (
        f"A system diagnostic just completed and found these issues:\n\n{lines}\n\n"
        "Write a brief spoken summary for Ky covering each issue and the exact action needed to fix it. "
        "Include relevant links (e.g. elevenlabs.io/subscription for credit issues). "
        "Be direct and specific. Plain text only, no markdown headers."
    )
    try:
        # Use a plain Anthropic call — no tools, no loop risk
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        resp   = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=512,
            system="You are Tina, a concise AI assistant. Write short, actionable spoken summaries.",
            messages=[{"role": "user", "content": prompt}],
        )
        review = next((b.text for b in resp.content if hasattr(b, "text")), "")
        if review:
            await broadcast({"type": "response", "text": review})
            asyncio.create_task(_tts_stream(review[:300]))
            print(f"[diag_review] {review[:80]}...")
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
    """HTTP chat endpoint for external callers."""
    text   = body.get("text", "").strip()
    source = body.get("source", "api")
    if not text:
        return {"reply": ""}
    label = f"[{source.upper()}] {text}"
    await broadcast({"type": "heard", "text": label})
    async with _agent_lock:
        reply = await agent.chat(text, background=False)
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply, list(agent.history)))
    asyncio.create_task(_tts_stream(reply))
    return {"reply": reply}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    await ws.send_json({"type": "state", "state": "listening"})
    await ws.send_json({"type": "prefs", "data": _load_prefs()})
    await ws.send_json({"type": "gaming_mode", "active": _gaming_mode})

    # Re-hydrate dashboard with any agents that are already running
    # (happens after a backend restart — tasks resume but frontend reconnects cold)
    from tina.agent_state import get_all_active
    for agent_key, info in get_all_active().items():
        meta = _AGENT_META.get(agent_key, {"display": agent_key.capitalize(), "color": "#8B5CF6", "glow": "#A78BFA"})
        await ws.send_json({
            "type":    "agent_background_start",
            "agent":   meta["display"],
            "key":     agent_key,
            "color":   meta.get("color", "#8B5CF6"),
            "glow":    meta.get("glow",  "#A78BFA"),
            "task":    info["task"][:120],
        })
        if info.get("current"):
            await ws.send_json({
                "type": "tool",
                "name": info["current"],
                "time": datetime.now().strftime("%H:%M:%S"),
            })
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

                elif msg_type == "pause_wake_word":
                    from tina import wake_word as _ww
                    _ww.pause()

                elif msg_type == "resume_wake_word":
                    from tina import wake_word as _ww
                    _ww.resume()

                elif msg_type == "set_gaming_mode":
                    await _set_gaming_mode(bool(data.get("value")))

                elif msg_type == "reset":
                    agent.reset()

    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)
