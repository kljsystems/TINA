import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BASE_DIR

RESTART_FLAG = os.path.join(BASE_DIR, "data", "restart.flag")
LOG_FILE     = os.path.join(BASE_DIR, "data", "backend.log")
_DOCS_DIR          = os.path.join(BASE_DIR, "docs")
_CHANGE_NOTES_FILE = os.path.join(_DOCS_DIR, "SAM_CHANGE_NOTES.md")


def check_backend_liveness(attempts: int = 5) -> tuple:
    """
    Real liveness check: probe /api/status with retries and short timeouts.
    Returns (alive: bool, message: str).
    Reused by verify_backend tool and startup_changes.py verification — extracted here
    so both callers share identical retry/timeout logic with no duplication.
    """
    import time
    import httpx

    if os.path.exists(RESTART_FLAG):
        return False, "Restart is still in progress — the flag file hasn't been consumed yet."

    for attempt in range(1, attempts + 1):
        try:
            r = httpx.get("http://localhost:8000/api/status", timeout=3.0)
            if r.status_code == 200:
                return True, (
                    f"Backend is up and responding (confirmed on attempt {attempt}/{attempts}). "
                    "Self-modification task is safe to report as COMPLETE."
                )
        except Exception:
            pass
        if attempt < attempts:
            time.sleep(1)

    return (
        False,
        (
            f"BACKEND IS NOT RESPONDING — all {attempts} liveness probes to /api/status failed. "
            "Do NOT report this task as complete. "
            "Investigate immediately: call read_backend_logs to see the startup crash, "
            "then git revert to the pre-change commit, restart_backend, and verify_backend again."
        ),
    )

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
            "that require a fresh process — the flag is picked up by tina.py within ~1 second, "
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
            "Confirm the backend is actually alive after a restart or self-modification. "
            "Performs a REAL liveness check: verifies the restart flag is gone, then probes "
            "/api/status with retries (5 attempts, 3s timeout each). "
            "REQUIRED after any restart_backend call on TINA's own code. "
            "A passing result is the only valid proof the backend came back up — "
            "do NOT report a self-modification task as complete without calling this first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "write_change_note",
        "description": (
            "Append a timestamped entry to docs/SAM_CHANGE_NOTES.md — a cross-device running log "
            "of code changes Sam has made. Call after completing any task that modifies code files "
            "so the next session (possibly on a different machine) has human-readable context "
            "beyond the bare git diff. Append-only — never overwrites existing notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type":        "string",
                    "description": "Brief description of what changed and why.",
                },
                "files": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "List of file paths that were modified.",
                },
                "risk_notes": {
                    "type":        "string",
                    "description": "Any risks, known issues, or follow-up needed.",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "open_terminal",
        "description": (
            "Open a new terminal window in the specified directory so Ky can run a command — "
            "typically pip install or npm install when a new dependency is needed. "
            "The terminal opens with the command printed prominently so Ky just has to type it and press Enter. "
            "Always call this instead of asking Ky to open a terminal himself. "
            "Also update requirements.txt or package.json yourself before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type":        "string",
                    "description": "The exact command Ky needs to run, e.g. 'pip install pandas openpyxl'.",
                },
                "directory": {
                    "type":        "string",
                    "description": "Absolute path to open the terminal in. Defaults to TINA root if omitted.",
                },
                "reason": {
                    "type":        "string",
                    "description": "Why this package is needed — shown in the terminal so Ky has context.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "open_browser",
        "description": (
            "Open a file or URL in Ky's default browser. "
            "Pass a local file path (e.g. C:\\Users\\...\\Sites\\mysite\\index.html) to open it as a file:// page, "
            "or a full URL (http://localhost:5173) to open a running dev server. "
            "Use after building or updating a site so Ky can see it immediately. "
            "Follow up with take_screenshot to verify the rendered result yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type":        "string",
                    "description": "Absolute file path or full URL to open.",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "show_email_drafts",
        "description": (
            "Show Ky's pending email drafts from the last triage run as a review overlay on the dashboard. "
            "Each draft shows the sender, subject line, and Tristan's drafted reply. "
            "Ky can then send or skip each one. "
            "Use when Ky says 'show me my drafts', 'what emails need replies', "
            "'review my emails', 'show pending replies', or similar."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "take_screenshot",
        "description": (
            "Take a full screenshot of Ky's current screen and return it as an image you can see. "
            "Use when Ky says 'what does this look like', 'can you see my screen', 'check this', "
            "'what's on screen', or when you need to visually verify a result after opening a browser "
            "page, running Sam's code, or checking a deployed site. "
            "Returns the screen as a visible image — describe what you see."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "morning_briefing",
        "description": (
            "Trigger the full morning routine — opens Google Calendar in the browser, "
            "sends popup cards for weather, today's schedule, Stripe revenue, and KAOS health, "
            "then speaks a synthesised briefing. "
            "Call this when Ky says 'good morning', 'morning briefing', 'start my day', "
            "or any similar greeting at the start of the day."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "dashboard_popup",
        "description": (
            "Push a data card to the dashboard as a featured overlay panel that auto-dismisses. "
            "Use this during morning routine to surface KAOS health, Stripe MRR, email summary, "
            "and other key metrics — call it once per data source so cards stack. "
            "Also use when Ky explicitly asks to 'show me' something on the dashboard. "
            "Keep content concise: 3-6 bullet points or key numbers. Plain text only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short card header (e.g. 'KAOS HEALTH', 'STRIPE REVENUE', 'EMAIL').",
                },
                "content": {
                    "type": "string",
                    "description": "Data to display. 3-6 lines, key numbers only. Plain text.",
                },
                "color": {
                    "type": "string",
                    "description": "Accent colour hex. Default #8B5CF6 (purple). Use #4ade80 (green) for healthy, #f59e0b (amber) for warnings, #ef4444 (red) for alerts.",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Seconds before auto-dismiss. Default 45.",
                },
            },
            "required": ["title", "content"],
        },
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
            return "No backend log found. Start the backend via tina.py first."
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
        # Write restart flag — tina.py watcher picks this up within ~1 second
        with open(RESTART_FLAG, "w") as f:
            f.write(reason)
        # Write post-restart sentinel — main.py reads this on next startup to announce outcome
        sentinel = os.path.join(data_dir, "post_restart.json")
        with open(sentinel, "w") as f:
            _json.dump({"reason": reason}, f)
        return (
            "Restart flag written. tina.py will terminate and relaunch the backend within ~1 second. "
            "The WebSocket should reconnect automatically in ~3–5 seconds. "
            f"Reason: {reason or 'not specified'}"
        )

    if name == "verify_backend":
        alive, message = check_backend_liveness()
        return message

    if name == "write_change_note":
        from datetime import datetime as _dt
        summary    = inputs.get("summary", "").strip()
        files      = inputs.get("files") or []
        risk_notes = inputs.get("risk_notes", "").strip()
        if not summary:
            return "write_change_note requires a summary."
        os.makedirs(_DOCS_DIR, exist_ok=True)
        now_str   = _dt.now().strftime("%Y-%m-%d %H:%M")
        file_list = "\n".join(f"  - {f}" for f in files) if files else "  (no files listed)"
        risk_line = f"\n**Risks/Notes:** {risk_notes}" if risk_notes else ""
        entry = (
            f"\n---\n\n"
            f"## {now_str}\n\n"
            f"**Summary:** {summary}\n\n"
            f"**Files changed:**\n{file_list}"
            f"{risk_line}\n"
        )
        try:
            with open(_CHANGE_NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            return f"Change note appended to docs/SAM_CHANGE_NOTES.md ({now_str})"
        except Exception as e:
            return f"Could not write change note: {e}"

    if name == "open_terminal":
        import subprocess
        command   = inputs.get("command", "")
        directory = inputs.get("directory", BASE_DIR)
        reason    = inputs.get("reason", "")

        if not os.path.isdir(directory):
            directory = BASE_DIR

        # PowerShell startup script: print the command clearly, then stay open
        reason_line = f"Write-Host '  Reason : {reason}' -ForegroundColor DarkGray; " if reason else ""
        ps_init = (
            "Write-Host ''; "
            "Write-Host '  TINA needs you to run this command:' -ForegroundColor Cyan; "
            f"{reason_line}"
            "Write-Host ''; "
            f"Write-Host '  {command}' -ForegroundColor Yellow; "
            "Write-Host ''; "
            "Write-Host '  Copy the line above, paste it here, and press Enter.' -ForegroundColor DarkGray; "
            "Write-Host '  When done, you can close this window.' -ForegroundColor DarkGray; "
            "Write-Host ''"
        )

        launched = False

        # Try Windows Terminal (wt.exe) — available on Windows 10/11
        try:
            subprocess.Popen(
                ["wt.exe", "-d", directory, "--title", f"TINA — {command}",
                 "powershell.exe", "-NoExit", "-Command", ps_init],
                creationflags=subprocess.DETACHED_PROCESS,
            )
            launched = True
        except FileNotFoundError:
            pass

        # Fall back to a plain PowerShell window
        if not launched:
            try:
                subprocess.Popen(
                    ["powershell.exe", "-NoExit", "-Command",
                     f"Set-Location '{directory}'; {ps_init}"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                launched = True
            except FileNotFoundError:
                pass

        # Last resort: cmd
        if not launched:
            try:
                subprocess.Popen(
                    ["cmd.exe", "/K", f"cd /d \"{directory}\" && echo Run: {command}"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                launched = True
            except FileNotFoundError:
                pass

        if not launched:
            return (
                f"Could not open a terminal automatically. "
                f"Please open a terminal in {directory} and run:\n\n  {command}"
            )

        return (
            f"Terminal opened in {directory}.\n"
            f"Command for Ky to run:  {command}\n"
            f"{('Reason: ' + reason) if reason else ''}"
        ).strip()

    if name == "open_browser":
        import webbrowser
        from urllib.request import pathname2url
        target = inputs.get("target", "").strip()
        if not target:
            return "No target provided."
        if target.startswith("http://") or target.startswith("https://") or target.startswith("file://"):
            url = target
        else:
            # Normalise Windows path and verify the file exists before opening
            norm = os.path.normpath(target)
            if not os.path.exists(norm):
                return f"File not found: {norm} — check the path and try again."
            url = "file:///" + pathname2url(norm).lstrip("/")
        opened = webbrowser.open(url)
        return f"Opened in browser: {url}" if opened else f"Could not open browser for: {url}"

    if name == "show_email_drafts":
        import httpx as _httpx
        try:
            r = _httpx.post("http://localhost:8000/api/show-email-drafts", timeout=30)
            data = r.json()
            drafts = data.get("drafts", [])
            if not drafts:
                return "No pending email drafts found in the last triage report."
            urgent = sum(1 for d in drafts if d.get("priority") == "URGENT")
            normal = len(drafts) - urgent
            parts = []
            if urgent: parts.append(f"{urgent} urgent")
            if normal: parts.append(f"{normal} normal")
            return f"Showing {len(drafts)} draft{'s' if len(drafts) != 1 else ''} ({', '.join(parts)}) on your dashboard."
        except Exception as e:
            return f"Could not load drafts: {e}"

    if name == "take_screenshot":
        try:
            from PIL import ImageGrab
            import io as _io, base64 as _b64
            img  = ImageGrab.grab()
            buf  = _io.BytesIO()
            # Downscale if very large (keeps tokens manageable)
            if img.width > 1920:
                ratio = 1920 / img.width
                img   = img.resize((1920, int(img.height * ratio)))
            img.save(buf, format="PNG", optimize=True)
            data = _b64.b64encode(buf.getvalue()).decode()
            return {"__type": "image", "data": data, "media_type": "image/png",
                    "text": f"Screenshot captured ({img.width}×{img.height})"}
        except ImportError:
            return "Screenshot requires Pillow — run: pip install Pillow"
        except Exception as e:
            return f"Screenshot failed: {e}"

    if name == "morning_briefing":
        import httpx as _httpx
        try:
            _httpx.post("http://localhost:8000/api/briefing", timeout=5)
            return "Morning routine started — opening calendar and sending dashboard cards now."
        except Exception as e:
            return f"Could not trigger morning routine: {e}"

    if name == "dashboard_popup":
        import httpx as _httpx
        import uuid as _uuid
        import time as _time
        title   = inputs.get("title",  "INFO")
        content = inputs.get("content", "")
        color   = inputs.get("color",  "#8B5CF6")
        ttl     = int(inputs.get("ttl", 45)) * 1000
        payload = {
            "id":      str(_uuid.uuid4()),
            "title":   title,
            "content": content,
            "color":   color,
            "ttl":     ttl,
            "ts":      int(_time.time() * 1000),
        }
        try:
            _httpx.post("http://localhost:8000/api/broadcast-panel", json=payload, timeout=5).raise_for_status()
            return f"Dashboard popup sent: {title}"
        except Exception as e:
            return f"Could not send popup ({e}) — logging content instead:\n{title}\n{content}"

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
