"""Launch TINA backend + frontend from a single terminal. Ctrl+C stops both."""
import asyncio
import os
import signal
import subprocess
import sys
import time
import threading

# Force UTF-8 so Tina's responses (with emojis etc.) print correctly on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT         = os.path.dirname(os.path.abspath(__file__))
RESTART_FLAG = os.path.join(ROOT, "data", "restart.flag")
LOG_FILE     = os.path.join(ROOT, "data", "backend.log")

CRASH_WINDOW = 120  # seconds — window used to detect a crash loop
MAX_CRASHES  = 3    # crashes within window before Sam is called

_backend:       subprocess.Popen | None = None
_frontend:      subprocess.Popen | None = None
_shutting_down: bool = False
_crash_times:   list[float] = []


# ── Logging ───────────────────────────────────────────────────────────────────

def _tee_backend(proc: subprocess.Popen) -> None:
    """Read backend stdout/stderr, write to terminal AND data/backend.log."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            lf.write(text)
            lf.flush()


def _read_crash_logs(lines: int = 120) -> str:
    """Return recent error-relevant log lines for Sam to diagnose."""
    if not os.path.exists(LOG_FILE):
        return "No log file found."
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    error_lines = [l for l in all_lines if any(
        kw in l.lower() for kw in ["error", "exception", "traceback", "critical", "==="]
    )]
    recent = (error_lines or all_lines)[-lines:]
    return "".join(recent)


# ── Sam crash-fix invocation ──────────────────────────────────────────────────

async def _invoke_sam(crash_logs: str) -> None:
    """Import and run CodingAgent directly to diagnose and fix the crash."""
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    try:
        from tina.agents.coding import CodingAgent
    except Exception as e:
        print(f"  [TINA] Could not import CodingAgent: {e}")
        return

    task = (
        "EMERGENCY FAILSAFE — The TINA backend has crashed 3 times in under 2 minutes and is down.\n\n"
        f"Recent error logs:\n{crash_logs}\n\n"
        "Your job:\n"
        "1. Read the error logs to identify the exact root cause\n"
        "2. Use fs_read on the relevant source files\n"
        "3. Fix the bug — write corrected files to disk with fs_write\n"
        "4. Do NOT call restart_backend — tina.py will restart after you finish\n\n"
        "Fix only the crash. Be fast and focused."
    )

    try:
        sam    = CodingAgent()
        result = await sam.run(task)
        summary = result[:300] + "..." if len(result) > 300 else result
        print(f"  [TINA] Sam's fix applied:\n  {summary}\n")
    except Exception as e:
        print(f"  [TINA] Sam diagnosis failed: {e}")
        print(f"  [TINA] Manual intervention needed — backend is in a crash loop.")


def _handle_crash_loop() -> None:
    """Called from the supervisor thread — runs Sam synchronously via asyncio.run()."""
    crash_logs = _read_crash_logs()
    print("  [TINA] Crash loop detected — calling Sam to diagnose and fix...")
    asyncio.run(_invoke_sam(crash_logs))


# ── Process management ────────────────────────────────────────────────────────

def _start_backend() -> subprocess.Popen:
    global _backend
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== Backend started: {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    _backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    threading.Thread(target=_tee_backend, args=(_backend,), daemon=True).start()
    return _backend


def _supervisor() -> None:
    """
    Unified backend supervisor — runs in a background thread.
    Handles: explicit restarts (restart.flag), crash recovery, and crash loop diagnosis.
    """
    global _crash_times

    while not _shutting_down:
        time.sleep(0.5)

        if _backend is None:
            continue

        # Explicit restart requested by Tina or Sam
        if os.path.exists(RESTART_FLAG):
            try:
                os.remove(RESTART_FLAG)
            except Exception:
                pass
            print("\n  [TINA] Restart requested — stopping backend...")
            if _backend.poll() is None:
                _backend.terminate()
                _backend.wait()
            time.sleep(2)
            _start_backend()
            print("  [TINA] Backend restarted\n")
            continue

        # Check if backend exited unexpectedly
        exit_code = _backend.poll()
        if exit_code is None:
            continue  # still running

        if _shutting_down:
            break

        # Unexpected exit — crash recovery
        now = time.time()
        _crash_times.append(now)
        recent = [t for t in _crash_times if now - t < CRASH_WINDOW]

        print(f"\n  [TINA] Backend exited (code {exit_code}) — crash {len(recent)}/{MAX_CRASHES}")

        if len(recent) >= MAX_CRASHES:
            print("  [TINA] Crash loop detected — calling Sam to diagnose and fix...")
            _crash_times = []
            _handle_crash_loop()
            time.sleep(3)
        else:
            print("  [TINA] Restarting backend...")
            time.sleep(2)

        _start_backend()
        print("  [TINA] Backend back online\n")


def shutdown(sig=None, frame=None) -> None:
    global _shutting_down
    _shutting_down = True
    if _backend:
        _backend.terminate()
    if _frontend:
        _frontend.terminate()
    sys.exit(0)


# ── Entry point ───────────────────────────────────────────────────────────────

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

if os.path.exists(RESTART_FLAG):
    os.remove(RESTART_FLAG)

_start_backend()

_frontend = subprocess.Popen(
    "npm run dev",
    cwd=os.path.join(ROOT, "frontend"),
    shell=True,
)

threading.Thread(target=_supervisor, daemon=True).start()

print("\n  TINA online")
print("  Backend  → http://localhost:8000")
print("  Frontend → http://localhost:5173")
print("  Ctrl+C to stop\n")

_frontend.wait()
