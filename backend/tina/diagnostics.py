"""
System diagnostics — runs all service/token/agent checks and streams
results via the on_result callback as each check completes.
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from config import (
    ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, DEFAULT_VOICE_ID,
    DEEPGRAM_API_KEY, TAVILY_API_KEY, OPENWEATHER_API_KEY,
    GITHUB_TOKEN, SUPABASE_URL, SUPABASE_KEY,
    SLACK_TINA_BOT_TOKEN, SLACK_SAM_BOT_TOKEN,
    VAULT_DIR, PROJECTS, DATA_DIR,
)

# Ordered list of (check_id, display_label)
CHECKS = [
    ("anthropic",   "ANTHROPIC API"),
    ("elevenlabs",  "ELEVENLABS TTS"),
    ("deepgram",    "DEEPGRAM STT"),
    ("tavily",      "TAVILY SEARCH"),
    ("openweather", "OPENWEATHER"),
    ("github",      "GITHUB"),
    ("supabase",    "SUPABASE DB"),
    ("slack_tina",  "SLACK · TINA"),
    ("slack_sam",   "SLACK · SAM"),
    ("calendar",    "GOOGLE CALENDAR"),
    ("vault",       "OBSIDIAN VAULT"),
    ("filesystem",  "FILESYSTEM"),
    ("memory_db",   "MEMORY DB"),
    ("pyttsx3",     "PYTTSX3 TTS"),
    ("agents",      "AGENTS"),
]


# ── Individual checks ─────────────────────────────────────────────────────────

async def _check_anthropic():
    if not ANTHROPIC_API_KEY:
        return "fail", "ANTHROPIC_API_KEY not set"
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1,
        messages=[{"role": "user", "content": "ping"}],
    )
    return "pass", f"OK · {resp.model}"


async def _check_elevenlabs():
    if not ELEVENLABS_API_KEY:
        return "fail", "ELEVENLABS_API_KEY not set"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
        )
        if r.status_code != 200:
            return "fail", f"HTTP {r.status_code}"
        sub       = r.json().get("subscription", {})
        used      = sub.get("character_count", 0)
        limit     = sub.get("character_limit", 0)
        remaining = limit - used
        tier      = sub.get("tier", "unknown")
        if remaining <= 0:
            return "fail", f"0 credits remaining · tier: {tier}"
        if remaining < 1000:
            return "warn", f"{remaining:,} credits left · tier: {tier}"
        return "pass", f"{remaining:,} / {limit:,} credits · tier: {tier}"


async def _check_deepgram():
    if not DEEPGRAM_API_KEY:
        return "fail", "DEEPGRAM_API_KEY not set"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        )
        if r.status_code == 200:
            projects = r.json().get("projects", [])
            return "pass", f"{len(projects)} project(s) found"
        return "fail", f"HTTP {r.status_code}"


async def _check_tavily():
    if not TAVILY_API_KEY:
        return "fail", "TAVILY_API_KEY not set"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_API_KEY, "query": "test", "max_results": 1},
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            return "pass", f"Search OK · {len(results)} result(s)"
        return "fail", f"HTTP {r.status_code}: {r.text[:80]}"


async def _check_openweather():
    if not OPENWEATHER_API_KEY:
        return "fail", "OPENWEATHER_API_KEY not set"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": "Sydney", "appid": OPENWEATHER_API_KEY},
        )
        if r.status_code == 200:
            data = r.json()
            return "pass", f"Sydney: {data.get('weather', [{}])[0].get('description', 'OK')}"
        return "fail", f"HTTP {r.status_code}: {r.json().get('message', '')}"


async def _check_github():
    if not GITHUB_TOKEN:
        return "fail", "GITHUB_TOKEN not set"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
        )
        if r.status_code == 200:
            user = r.json().get("login", "unknown")
            return "pass", f"Authenticated as {user}"
        return "fail", f"HTTP {r.status_code}"


async def _check_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return "fail", "SUPABASE_URL or SUPABASE_KEY not set"
    def _test():
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        client.table("conversations").insert({
            "agent": "_diag", "session_id": "_diag", "role": "user", "content": "ping"
        }).execute()
        result = client.table("conversations").select("id").eq("agent", "_diag").execute()
        client.table("conversations").delete().eq("agent", "_diag").execute()
        return len(result.data)
    count = await asyncio.to_thread(_test)
    return "pass", f"Read/write OK · {count} test row(s) cleaned up"


async def _check_slack_tina():
    if not SLACK_TINA_BOT_TOKEN:
        return "fail", "SLACK_TINA_BOT_TOKEN not set"
    def _test():
        from slack_sdk import WebClient
        return WebClient(token=SLACK_TINA_BOT_TOKEN).auth_test()
    r = await asyncio.to_thread(_test)
    if r["ok"]:
        return "pass", f"@{r['user']} · team: {r.get('team', '?')}"
    return "fail", r.get("error", "auth failed")


async def _check_slack_sam():
    if not SLACK_SAM_BOT_TOKEN:
        return "fail", "SLACK_SAM_BOT_TOKEN not set"
    def _test():
        from slack_sdk import WebClient
        return WebClient(token=SLACK_SAM_BOT_TOKEN).auth_test()
    r = await asyncio.to_thread(_test)
    if r["ok"]:
        return "pass", f"@{r['user']} · team: {r.get('team', '?')}"
    return "fail", r.get("error", "auth failed")


async def _check_calendar():
    token_path = os.path.join(DATA_DIR, "token.json")
    if not os.path.exists(token_path):
        return "fail", "token.json not found — delete data/token.json and restart to re-auth"
    try:
        import json
        from datetime import datetime, timezone
        with open(token_path) as f:
            tok = json.load(f)
        expiry_str = tok.get("expiry") or tok.get("token_expiry", "")
        if expiry_str:
            expiry_dt = datetime.fromisoformat(str(expiry_str).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if expiry_dt < now:
                return "warn", f"Token expired {expiry_str[:19]} — will auto-refresh on next use"
        return "pass", f"Token valid · expiry: {str(expiry_str)[:19]}"
    except Exception as e:
        return "warn", f"Token file exists but unreadable: {e}"


async def _check_vault():
    vault = VAULT_DIR
    if not os.path.isdir(vault):
        return "fail", f"Vault not found: {vault}"
    md_files = sum(1 for root, _, files in os.walk(vault) for f in files if f.endswith(".md"))
    return "pass", f"{md_files:,} notes in vault"


async def _check_filesystem():
    results = []
    for name, path in PROJECTS.items():
        if os.path.isdir(path):
            count = len(os.listdir(path))
            results.append(f"{name}: OK ({count} items)")
        else:
            results.append(f"{name}: MISSING")
    any_missing = any("MISSING" in r for r in results)
    status = "warn" if any_missing else "pass"
    return status, " · ".join(results)


async def _check_memory_db():
    if not SUPABASE_URL:
        return "warn", "Supabase not configured — skipped"
    from tina.memory_db import save_turn, load_history
    import uuid
    sid = f"_diag_{uuid.uuid4().hex[:8]}"
    await save_turn("_diag_test", sid, "user", "ping")
    rows = await load_history("_diag_test", limit=1)
    # Clean up
    def _cleanup():
        from supabase import create_client
        create_client(SUPABASE_URL, SUPABASE_KEY).table("conversations").delete().eq("agent", "_diag_test").execute()
    await asyncio.to_thread(_cleanup)
    if rows:
        return "pass", f"Save/load OK · {len(rows)} row(s) verified"
    return "fail", "Row not found after save"


async def _check_pyttsx3():
    def _test():
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        engine.stop()
        return len(voices)
    count = await asyncio.to_thread(_test)
    return "pass", f"{count} voice(s) available"


async def _check_agents():
    try:
        from tina.agents.coding    import CodingAgent
        from tina.agents.research  import ResearchAgent
        from tina.agents.email     import EmailAgent
        from tina.agents.data      import DataAgent
        from tina.agents.marketing import MarketingAgent
        sam     = CodingAgent()
        charlie = ResearchAgent()
        tristan = EmailAgent()
        connor  = DataAgent()
        wade    = MarketingAgent()
        return "pass", (
            f"{sam.name} ({len(sam._definitions)} tools) · "
            f"{charlie.name} ({len(charlie._definitions)} tools) · "
            f"{tristan.name} ({len(tristan._definitions)} tools) · "
            f"{connor.name} ({len(connor._definitions)} tools) · "
            f"{wade.name} ({len(wade._definitions)} tools)"
        )
    except Exception as e:
        return "fail", str(e)[:100]


_RUNNERS = {
    "anthropic":   _check_anthropic,
    "elevenlabs":  _check_elevenlabs,
    "deepgram":    _check_deepgram,
    "tavily":      _check_tavily,
    "openweather": _check_openweather,
    "github":      _check_github,
    "supabase":    _check_supabase,
    "slack_tina":  _check_slack_tina,
    "slack_sam":   _check_slack_sam,
    "calendar":    _check_calendar,
    "vault":       _check_vault,
    "filesystem":  _check_filesystem,
    "memory_db":   _check_memory_db,
    "pyttsx3":     _check_pyttsx3,
    "agents":      _check_agents,
}


async def run_all(on_result):
    """
    Run all checks concurrently. Calls on_result(id, label, status, detail) as each finishes.
    status is one of: "pass", "fail", "warn"
    """
    async def _run(check_id, label):
        try:
            status, detail = await _RUNNERS[check_id]()
        except Exception as e:
            status, detail = "fail", str(e)[:120]
        await on_result(check_id, label, status, detail)

    await asyncio.gather(*[_run(cid, lbl) for cid, lbl in CHECKS])
