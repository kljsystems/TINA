"""Launch TINA backend + frontend from a single terminal. Ctrl+C stops both."""
import subprocess
import sys
import os
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))

procs: list[subprocess.Popen] = []

def shutdown(sig=None, frame=None):
    for p in procs:
        p.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000", "--reload"],
    cwd=ROOT,
)
frontend = subprocess.Popen(
    "npm run dev",
    cwd=os.path.join(ROOT, "frontend"),
    shell=True,
)

procs.extend([backend, frontend])

print("\n  TINA online")
print("  Backend  → http://localhost:8000")
print("  Frontend → http://localhost:5173")
print("  Ctrl+C to stop\n")

backend.wait()
frontend.wait()
