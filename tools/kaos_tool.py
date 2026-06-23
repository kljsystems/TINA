"""TINA Tool — KAOS operator console (Supabase + Sentry for KLJ's live SaaS platform)."""
import os
import random
import sys
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import (
        KAOS_SUPABASE_URL, KAOS_SUPABASE_SERVICE_KEY, KAOS_APP_URL,
        SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT,
    )
except ImportError:
    KAOS_SUPABASE_URL         = os.getenv("KAOS_SUPABASE_URL",         "")
    KAOS_SUPABASE_SERVICE_KEY = os.getenv("KAOS_SUPABASE_SERVICE_KEY", "")
    KAOS_APP_URL              = os.getenv("KAOS_APP_URL",              "")
    SENTRY_AUTH_TOKEN         = os.getenv("SENTRY_AUTH_TOKEN",         "")
    SENTRY_ORG                = os.getenv("SENTRY_ORG",                "")
    SENTRY_PROJECT            = os.getenv("SENTRY_PROJECT",            "")

DEFINITIONS = [
    {
        "name": "kaos_overview",
        "description": (
            "Get a live developer overview of KAOS — workspace count, active user count, "
            "waitlist size, open support tickets, and subscription status. "
            "Use in morning briefings or when Ky asks how KAOS is doing."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kaos_support_tickets",
        "description": (
            "List support tickets submitted by KAOS users — bug reports and feature requests. "
            "Shows submitter name, email, workspace, title, description, type, and status. "
            "Default shows open tickets only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type":        "string",
                    "enum":        ["open", "in_progress", "resolved", "wont_fix", "all"],
                    "description": "Filter by ticket status. Default: open.",
                },
                "limit": {
                    "type":        "integer",
                    "description": "Max tickets to return. Default: 20.",
                },
            },
        },
    },
    {
        "name": "kaos_update_ticket",
        "description": (
            "Update a KAOS support ticket — change its status, set priority, or add developer notes. "
            "Use after reviewing a ticket to mark it in progress, resolved, or won't fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id":       {"type": "string", "description": "Ticket ID to update."},
                "status":   {"type": "string", "enum": ["open", "in_progress", "resolved", "wont_fix"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "notes":    {"type": "string", "description": "Developer notes to add to the ticket."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "kaos_waitlist",
        "description": "Get KAOS waitlist data — total signups, recent entries, and email list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Recent signups to show. Default: 10."},
            },
        },
    },
    {
        "name": "kaos_beta_users",
        "description": (
            "List all KAOS beta users — who used a beta key, their workspace name, "
            "which modules they have active, and when they joined."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kaos_subscriptions",
        "description": (
            "Get Stripe subscription data for all KAOS workspaces — "
            "active, trialing, and cancelled counts, plus which workspace is on which plan."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "kaos_generate_beta_key",
        "description": (
            "Generate a new KAOS beta access key. "
            "Use when Ky wants to invite someone to KAOS. "
            "Optionally assign to a specific email or label it with a company name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Label for this key, e.g. the company name."},
                "email": {"type": "string", "description": "Email to pre-assign this key to."},
            },
        },
    },
    {
        "name": "kaos_errors",
        "description": (
            "Get recent KAOS application errors from Sentry.io. "
            "Shows unresolved issues by default — error title, level, event count, first/last seen. "
            "Use when Ky asks about KAOS errors or after a monitor alert fires."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level":    {"type": "string", "enum": ["error", "warning", "fatal", "all"], "description": "Severity filter. Default: error."},
                "limit":    {"type": "integer", "description": "Max issues to return. Default: 20."},
                "query":    {"type": "string",  "description": "Optional Sentry search query, e.g. 'is:unresolved assigned:me'. Default: 'is:unresolved'."},
            },
        },
    },
    {
        "name": "kaos_resolve_error",
        "description": "Resolve a Sentry issue for KAOS — marks it as fixed. Use the issue ID from kaos_errors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string", "description": "Sentry issue ID to resolve."},
            },
            "required": ["issue_id"],
        },
    },
]


def _client():
    if not KAOS_SUPABASE_URL or not KAOS_SUPABASE_SERVICE_KEY:
        raise ValueError(
            "KAOS not configured — add KAOS_SUPABASE_URL and KAOS_SUPABASE_SERVICE_KEY "
            "to your .env file (copy from KAOS/.env.local: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)."
        )
    from supabase import create_client
    return create_client(KAOS_SUPABASE_URL, KAOS_SUPABASE_SERVICE_KEY)


def _generate_beta_code() -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    seg = lambda: "".join(random.choice(chars) for _ in range(4))
    return f"{seg()}-{seg()}-{seg()}"


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        return iso[:10]
    except Exception:
        return str(iso)


# ── Tool handlers ──────────────────────────────────────────────────────────────

def _kaos_overview() -> str:
    db = _client()

    ws      = (db.table("workspaces").select("id").execute().data or [])
    members = (db.table("workspace_members").select("id").eq("status", "active").execute().data or [])
    wl      = (db.table("waitlist").select("id").execute().data or [])
    tickets = (db.table("support_tickets").select("id, status").execute().data or [])
    subs    = (db.table("workspace_subscriptions").select("status").execute().data or [])
    keys    = (db.table("beta_keys").select("id, used_at, revoked").execute().data or [])

    open_tickets  = [t for t in tickets if t.get("status") not in ("resolved", "wont_fix")]
    active_subs   = sum(1 for s in subs if s.get("status") == "active")
    trialing_subs = sum(1 for s in subs if s.get("status") == "trialing")
    cancelled_subs= sum(1 for s in subs if s.get("status") == "cancelled")
    used_keys     = sum(1 for k in keys if k.get("used_at") and not k.get("revoked"))
    total_keys    = len(keys)

    return (
        f"KAOS OVERVIEW — {datetime.now().strftime('%d %b %Y %H:%M')}\n"
        f"Workspaces:        {len(ws)}\n"
        f"Active members:    {len(members)}\n"
        f"Beta keys used:    {used_keys} / {total_keys}\n"
        f"Waitlist:          {len(wl)}\n"
        f"Open tickets:      {len(open_tickets)} (of {len(tickets)} total)\n"
        f"Subscriptions:     {active_subs} active · {trialing_subs} trialing · {cancelled_subs} cancelled"
    )


def _kaos_support_tickets(status: str = "open", limit: int = 20) -> str:
    db      = _client()
    query   = db.table("support_tickets").select("*").order("created_at", desc=True).limit(limit)
    if status != "all":
        query = query.eq("status", status)
    rows = (query.execute().data or [])
    if not rows:
        return f"No {status} support tickets found."
    lines = [f"SUPPORT TICKETS ({status.upper()}) — {len(rows)} found\n"]
    for t in rows:
        lines.append(
            f"[{t.get('id','')}] {_fmt_date(t.get('created_at'))} | "
            f"Type: {t.get('type','?')} | Status: {t.get('status','?')} | "
            f"Priority: {t.get('priority','?')}\n"
            f"  From:  {t.get('submitted_by_name','?')} <{t.get('submitted_by_email','?')}>\n"
            f"  Title: {t.get('title','')}\n"
            f"  {t.get('description','')[:300]}\n"
        )
    return "\n".join(lines)


def _kaos_update_ticket(id: str, status: str = None, priority: str = None, notes: str = None) -> str:
    db = _client()
    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if status:   updates["status"]   = status
    if priority: updates["priority"] = priority
    if notes:    updates["notes"]    = notes
    if len(updates) == 1:
        return "Nothing to update — provide status, priority, or notes."
    db.table("support_tickets").update(updates).eq("id", id).execute()
    return f"Ticket {id} updated: {', '.join(f'{k}={v}' for k, v in updates.items() if k != 'updated_at')}"


def _kaos_waitlist(limit: int = 10) -> str:
    db   = _client()
    rows = (db.table("waitlist").select("*").order("created_at", desc=True).execute().data or [])
    if not rows:
        return "Waitlist is empty."
    recent = rows[:limit]
    lines = [f"KAOS WAITLIST — {len(rows)} total signups\n", f"Most recent {len(recent)}:"]
    for w in recent:
        name = w.get("name") or "no name"
        lines.append(f"  {_fmt_date(w.get('created_at'))}  {w.get('email','?')} ({name})")
    return "\n".join(lines)


def _kaos_beta_users() -> str:
    db = _client()
    keys    = (db.table("beta_keys").select("*").not_("used_at", "is", "null").eq("revoked", False).order("used_at", desc=True).execute().data or [])
    if not keys:
        return "No active beta users found."

    user_ids = [k["used_by_user_id"] for k in keys if k.get("used_by_user_id")]
    members  = (db.table("workspace_members").select("user_id, workspace_id, workspaces(id, name)").in_("user_id", user_ids).eq("role", "owner").execute().data or []) if user_ids else []
    ws_ids   = [m["workspace_id"] for m in members if m.get("workspace_id")]
    modules  = (db.table("workspace_modules").select("workspace_id, module_id, status").in_("workspace_id", ws_ids).execute().data or []) if ws_ids else []

    lines = [f"KAOS BETA USERS — {len(keys)} active\n"]
    for k in keys:
        member = next((m for m in members if m.get("user_id") == k.get("used_by_user_id")), None)
        ws_name = member.get("workspaces", {}).get("name", "no workspace") if member else "no workspace"
        ws_id   = member.get("workspace_id") if member else None
        active_mods = [m["module_id"] for m in modules if m.get("workspace_id") == ws_id and m.get("status") in ("active", "trialing")]
        lines.append(
            f"  {_fmt_date(k.get('used_at'))}  {k.get('used_by_email','?')}\n"
            f"    Workspace: {ws_name}  |  Modules: {', '.join(active_mods) or 'none'}"
        )
    return "\n".join(lines)


def _kaos_subscriptions() -> str:
    db   = _client()
    subs = (db.table("workspace_subscriptions").select("*, workspaces(name)").execute().data or [])
    if not subs:
        return "No subscription records found."
    by_status: dict[str, list] = {}
    for s in subs:
        st = s.get("status", "unknown")
        by_status.setdefault(st, []).append(s)

    lines = [f"KAOS SUBSCRIPTIONS — {len(subs)} total\n"]
    for status, group in sorted(by_status.items()):
        lines.append(f"{status.upper()} ({len(group)}):")
        for s in group:
            ws_name = (s.get("workspaces") or {}).get("name", "?")
            end     = _fmt_date(s.get("current_period_end"))
            cancel  = " [cancelling]" if s.get("cancel_at_period_end") else ""
            lines.append(f"  {ws_name}  — renews {end}{cancel}")
    return "\n".join(lines)


def _kaos_generate_beta_key(label: str = None, email: str = None) -> str:
    db   = _client()
    code = _generate_beta_code()
    row  = {"code": code}
    if label: row["label"]              = label
    if email: row["assigned_to_email"]  = email
    db.table("beta_keys").insert(row).execute()
    msg = f"Beta key generated: {code}"
    if label: msg += f"  Label: {label}"
    if email: msg += f"  Assigned to: {email}"
    return msg


def _sentry_headers() -> dict:
    if not SENTRY_AUTH_TOKEN:
        raise ValueError("Sentry not configured — add SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT to .env")
    return {"Authorization": f"Bearer {SENTRY_AUTH_TOKEN}"}


def _kaos_errors(level: str = "error", limit: int = 20, query: str = "is:unresolved") -> str:
    if not SENTRY_AUTH_TOKEN or not SENTRY_ORG or not SENTRY_PROJECT:
        return "Sentry not configured — add SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT to .env"

    params: dict = {"limit": limit, "sort": "date", "query": query}
    if level != "all":
        params["query"] = f"{params['query']} level:{level}"

    resp = httpx.get(
        f"https://sentry.io/api/0/projects/{SENTRY_ORG}/{SENTRY_PROJECT}/issues/",
        params=params,
        headers=_sentry_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    issues = resp.json()

    if not issues:
        return f"No issues found in Sentry (query: {params['query']})."

    lines = [f"KAOS SENTRY ERRORS — {len(issues)} issue(s)\n"]
    for i in issues:
        lines.append(
            f"  [{i.get('level','?').upper()}] ID:{i.get('id')}  {i.get('title','?')}\n"
            f"    Events: {i.get('count','?')} · Users: {i.get('userCount','?')} · "
            f"First: {_fmt_date(i.get('firstSeen'))} · Last: {_fmt_date(i.get('lastSeen'))}\n"
            f"    {i.get('permalink','')}"
        )
    return "\n".join(lines)


def _kaos_resolve_error(issue_id: str) -> str:
    if not SENTRY_AUTH_TOKEN:
        return "Sentry not configured."
    resp = httpx.put(
        f"https://sentry.io/api/0/issues/{issue_id}/",
        json={"status": "resolved"},
        headers=_sentry_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return f"Sentry issue {issue_id} marked as resolved."


def sentry_new_issues_since(since_iso: str) -> list[dict]:
    """Used by the KAOS monitor — returns new Sentry issues since the given timestamp."""
    if not SENTRY_AUTH_TOKEN or not SENTRY_ORG or not SENTRY_PROJECT:
        return []
    try:
        resp = httpx.get(
            f"https://sentry.io/api/0/projects/{SENTRY_ORG}/{SENTRY_PROJECT}/issues/",
            params={"query": f"is:unresolved firstSeen:>{since_iso}", "sort": "date", "limit": 25},
            headers=_sentry_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


# ── Dispatch ───────────────────────────────────────────────────────────────────

def handle(name: str, inputs: dict) -> str:
    try:
        if name == "kaos_overview":
            return _kaos_overview()
        if name == "kaos_support_tickets":
            return _kaos_support_tickets(inputs.get("status", "open"), inputs.get("limit", 20))
        if name == "kaos_update_ticket":
            return _kaos_update_ticket(
                inputs.get("id", ""),
                inputs.get("status"),
                inputs.get("priority"),
                inputs.get("notes"),
            )
        if name == "kaos_waitlist":
            return _kaos_waitlist(inputs.get("limit", 10))
        if name == "kaos_beta_users":
            return _kaos_beta_users()
        if name == "kaos_subscriptions":
            return _kaos_subscriptions()
        if name == "kaos_generate_beta_key":
            return _kaos_generate_beta_key(inputs.get("label"), inputs.get("email"))
        if name == "kaos_errors":
            return _kaos_errors(inputs.get("level", "error"), inputs.get("limit", 20), inputs.get("query", "is:unresolved"))
        if name == "kaos_resolve_error":
            return _kaos_resolve_error(inputs.get("issue_id", ""))
        return f"Unknown tool: {name}"
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"KAOS tool error ({name}): {e}"
