import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BASE_DIR

RESTART_FLAG = os.path.join(BASE_DIR, "data", "restart.flag")

LOG_FILE = os.path.join(BASE_DIR, "data", "backend.log")

DEFINITIONS = [
    {
        "name": "read_backend_logs",
        "description": (
            "Read recent backend log output to check for errors, exceptions, or runtime behaviour. "
            "Use after making code changes to verify the backend started cleanly, "
            "or when debugging a reported error. "
            "Supports optional line count and a filter string (e.g. 'ERROR', 'Exception', 'traceback')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type":        "integer",
                    "description": "Number of recent log lines to return (default 80, max 300).",
                },
                "filter": {
                    "type":        "string",
                    "description": "Only return lines containing this string. Case-insensitive.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "restart_backend",
        "description": (
            "Restart the TINA backend process. Use after Sam makes Python, config, or .env changes "
            "that require a fresh process — the flag is picked up by start.py within ~1 second, "
            "the backend goes down and comes back up in ~3 seconds, and the dashboard reconnects automatically. "
            "Note: pure React/frontend changes don't need this — Vite HMR handles those instantly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type":        "string",
                    "description": "What changed that requires the restart (e.g. 'new pip package', 'backend code change').",
                },
            },
            "required": [],
        },
    },
    {
        "name": "verify_backend",
        "description": (
            "Check whether the backend is currently healthy after a restart or code change. "
            "Returns whether the backend process appears to be up, based on the absence of a restart flag."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_ui_pref",
        "description": (
            "Show or hide a dashboard UI element. Persisted to disk so the setting survives restarts. "
            "Use this when Ky asks to turn on or off a dashboard panel — e.g. 'hide the activity log', "
            "'turn off the log', 'show the activity log again'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key":   {"type": "string",  "enum": ["activity_log"], "description": "Which element to configure."},
                "value": {"type": "boolean", "description": "true = visible, false = hidden."},
            },
            "required": ["key", "value"],
        },
    },
]


def handle(name: str, inputs: dict) -> str:
    if name == "read_backend_logs":
        if not os.path.exists(LOG_FILE):
            return "No backend log found. Start the backend via start.py first."
        n          = min(int(inputs.get("lines", 80)), 300)
        filter_str = inputs.get("filter", "").lower()
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if filter_str:
            lines = [l for l in lines if filter_str in l.lower()]
        recent = lines[-n:]
        if not recent:
            return f"No log lines found{f' matching {filter_str!r}' if filter_str else ''}."
        header = f"Last {len(recent)} backend log lines{f' (filter: {filter_str!r})' if filter_str else ''}:\n\n"
        return header + "".join(recent)

    if name == "restart_backend":
        import json as _json
        reason = inputs.get("reason", "")
        data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        # Write restart flag — start.py watcher picks this up within ~1 second
        with open(RESTART_FLAG, "w") as f:
            f.write(reason)
        # Write post-restart sentinel — main.py reads this on next startup to announce outcome
        sentinel = os.path.join(data_dir, "post_restart.json")
        with open(sentinel, "w") as f:
            _json.dump({"reason": reason}, f)
        return (
            "Restart flag written. start.py will terminate and relaunch the backend within ~1 second. "
            "The WebSocket should reconnect automatically in ~3–5 seconds. "
            "I'll post to Slack once I'm back online. "
            f"Reason: {reason or 'not specified'}"
        )

    if name == "verify_backend":
        if os.path.exists(RESTART_FLAG):
            return "Restart is still in progress — the flag file hasn't been consumed yet."
        return "No pending restart flag. Backend should be running normally."

    if name == "set_ui_pref":
        import json as _json
        from config import PREFS_FILE
        key   = inputs.get("key", "")
        value = inputs.get("value", True)
        prefs = {}
        if os.path.exists(PREFS_FILE):
            try:
                with open(PREFS_FILE) as f:
                    prefs = _json.load(f)
            except Exception:
                pass
        prefs[key] = value
        os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
        with open(PREFS_FILE, "w") as f:
            _json.dump(prefs, f, indent=2)
        state = "visible" if value else "hidden"
        return f"Dashboard {key.replace('_', ' ')} is now {state}."

    return f"Unknown tool: {name}"
