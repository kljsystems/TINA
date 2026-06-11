import os
import sys
import subprocess
import urllib.request
import urllib.error
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_URL = "http://localhost:8000"

DEFINITIONS = [
    {
        "name": "health_check",
        "description": (
            "Verify the backend is running and all services are reachable. "
            "Hits /api/status and returns which integrations are configured and online. "
            "Call this after restarting the backend to confirm it came up cleanly."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_tests",
        "description": (
            "Run the project test suite with pytest and return the full output. "
            "If no tests exist, reports that clearly. "
            "Use after making changes to verify nothing is broken."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Subdirectory or file to run tests from (default: project root).",
                },
                "filter": {
                    "type":        "string",
                    "description": "pytest -k filter expression to run specific tests.",
                },
            },
            "required": [],
        },
    },
]


def handle(name: str, inputs: dict) -> str:
    if name == "health_check":
        return _health_check()

    if name == "run_tests":
        return _run_tests(
            path=inputs.get("path", ""),
            filter_expr=inputs.get("filter", ""),
        )

    return f"Unknown tool: {name}"


def _health_check() -> str:
    try:
        with urllib.request.urlopen(f"{BACKEND_URL}/api/status", timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return (
            f"Backend is NOT reachable at {BACKEND_URL}.\n"
            f"Error: {e.reason}\n\n"
            "Check the logs with read_backend_logs — the process may have crashed on startup."
        )
    except Exception as e:
        return f"Health check failed unexpectedly: {e}"

    lines = [f"Backend is UP at {BACKEND_URL}\n", "Service configuration:"]
    all_ok = True
    for service, ok in data.items():
        status = "configured" if ok else "MISSING"
        if not ok:
            all_ok = False
        lines.append(f"  {service:<14} {status}")

    if not all_ok:
        lines.append("\nSome services are not configured — check .env for missing API keys.")
    else:
        lines.append("\nAll services configured.")

    return "\n".join(lines)


def _run_tests(path: str = "", filter_expr: str = "") -> str:
    from config import BASE_DIR

    test_root = os.path.join(BASE_DIR, path) if path else BASE_DIR

    # Check if any test files exist
    test_files = []
    for dirpath, _, filenames in os.walk(test_root):
        if any(skip in dirpath for skip in ["node_modules", ".git", "__pycache__", "venv"]):
            continue
        for fname in filenames:
            if fname.startswith("test_") or fname.endswith("_test.py"):
                test_files.append(os.path.join(dirpath, fname))

    if not test_files:
        return (
            "No test files found in the project (looking for test_*.py or *_test.py).\n\n"
            "The project has no test suite yet. Consider adding tests in a tests/ directory "
            "to get automated verification of key functionality."
        )

    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
    if filter_expr:
        cmd += ["-k", filter_expr]
    cmd.append(test_root)

    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        status = "PASSED" if result.returncode == 0 else "FAILED"
        return f"pytest {status} (exit code {result.returncode})\n\n{output}"
    except subprocess.TimeoutExpired:
        return "pytest timed out after 120 seconds."
    except FileNotFoundError:
        return "pytest is not installed. Run: pip install pytest"
    except Exception as e:
        return f"Test run failed: {e}"
