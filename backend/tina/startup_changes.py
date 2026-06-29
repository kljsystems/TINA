"""
TINA startup change detection — cross-device git diff tracking and auto-verification.

On every startup, compares HEAD against the last commit this machine ran on.
If new commits were pulled (i.e. someone pushed from another device), writes
docs/RECENT_CHANGES.md and optionally triggers lint + tests + liveness verification.

data/last_seen_commit.txt  — per-machine, gitignored, never committed
docs/RECENT_CHANGES.md     — per-machine snapshot, gitignored, overwritten each startup
docs/SAM_CHANGE_NOTES.md   — cross-device running log, committed, never overwritten
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Paths relative to this file's location: backend/tina/startup_changes.py
_HERE    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.normpath(os.path.join(_HERE, "..", ".."))  # → TINA repo root

LAST_SEEN_FILE     = os.path.join(BASE_DIR, "data", "last_seen_commit.txt")
DOCS_DIR           = os.path.join(BASE_DIR, "docs")
RECENT_CHANGES_FILE = os.path.join(DOCS_DIR, "RECENT_CHANGES.md")

# Paths that require mandatory verification when any changed file touches them
_CRITICAL_PREFIXES = ("backend/", "core/", "config.py")


def _git(*args) -> str:
    """Run a git command in the TINA root and return stdout (empty string on error)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"[startup-changes] git error: {e}")
        return ""


def detect_recent_changes() -> dict:
    """
    Compare current HEAD to the last-seen commit on this machine.
    If they differ, writes docs/RECENT_CHANGES.md and returns a summary dict.
    Updates data/last_seen_commit.txt to current HEAD on every run.

    Return keys:
      found (bool)               — True if new commits were detected
      first_run (bool, optional) — True if this is the first run on this machine
      commit_count (int)
      file_count (int)
      touches_critical_paths (bool) — True if backend/, core/, or config.py changed
      old_hash, new_hash (str)
      changed_files (list of (change_type, filepath))
      error (str, optional)
    """
    try:
        current_hash = _git("rev-parse", "HEAD")
        if not current_hash or len(current_hash) < 7:
            return {"found": False, "error": "Could not read HEAD — is this a git repo?"}

        # First run on this machine: save current hash, nothing to report
        if not os.path.exists(LAST_SEEN_FILE):
            os.makedirs(os.path.dirname(LAST_SEEN_FILE), exist_ok=True)
            with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
                f.write(current_hash)
            print(f"[startup-changes] first run on this machine — saved HEAD {current_hash[:8]}")
            return {"found": False, "first_run": True}

        with open(LAST_SEEN_FILE, encoding="utf-8") as f:
            last_hash = f.read().strip()

        # Guard: if stored hash is empty or identical to HEAD, nothing changed
        if not last_hash or last_hash == current_hash:
            # Always update so the file exists with a valid hash
            with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
                f.write(current_hash)
            return {"found": False}

        # Guard: verify stored hash is actually in repo history (may have been force-pushed)
        check = _git("cat-file", "-t", last_hash)
        if check != "commit":
            print(f"[startup-changes] stored hash {last_hash[:8]} not in repo — resetting")
            with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
                f.write(current_hash)
            return {"found": False}

        # --- Changes detected ---

        log_output = _git("log", f"{last_hash}..HEAD", "--oneline")
        commits = [line for line in log_output.splitlines() if line.strip()]

        diff_output = _git("diff", f"{last_hash}..HEAD", "--name-status")
        changed_files = []
        touches_critical = False
        type_map = {"A": "ADDED", "M": "MODIFIED", "D": "DELETED"}

        for line in diff_output.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                change_type = parts[0].strip()
                filepath    = parts[1].strip().replace("\\", "/")
                changed_files.append((change_type, filepath))
                if any(filepath.startswith(p) or filepath == p.rstrip("/")
                       for p in _CRITICAL_PREFIXES):
                    touches_critical = True

        # Write RECENT_CHANGES.md — point-in-time snapshot for this startup
        os.makedirs(DOCS_DIR, exist_ok=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        critical_header = (
            "\n> ⚠️ **CRITICAL PATH CHANGES DETECTED** — files under `backend/`, `core/`, or "
            "`config.py` were modified. Startup verification is mandatory.\n"
        ) if touches_critical else ""

        # Group changed files by top-level directory for readability
        grouped: dict = {}
        for ct, fp in changed_files:
            label = type_map.get(ct, ct)
            top   = fp.split("/")[0] if "/" in fp else "(root)"
            grouped.setdefault(top, []).append(f"  - [{label}] {fp}")

        file_section_lines = []
        for section in sorted(grouped):
            file_section_lines.append(f"\n### {section}/")
            file_section_lines.extend(grouped[section])

        commit_lines = "\n".join(f"- {c}" for c in commits) or "- (no commits listed)"
        file_section = "\n".join(file_section_lines) or "\n  (no files listed)"

        content = (
            f"# RECENT CHANGES — {now_str}\n\n"
            f"> Auto-generated by TINA on startup. Reflects commits pulled from git since "
            f"the last time TINA ran on this machine. Point-in-time snapshot — git is the "
            f"canonical change log. Overwritten on every startup where changes are detected.\n"
            f"{critical_header}\n"
            f"## Summary\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| Previous commit | `{last_hash[:12]}` |\n"
            f"| Current HEAD | `{current_hash[:12]}` |\n"
            f"| Commits pulled | {len(commits)} |\n"
            f"| Files changed | {len(changed_files)} |\n"
            f"| Touches critical paths | "
            f"{'**YES** — backend/, core/, or config.py' if touches_critical else 'No'} |\n\n"
            f"## Commits\n\n"
            f"{commit_lines}\n\n"
            f"## Changed Files\n"
            f"{file_section}\n\n"
            f"---\n"
            f"*VERIFICATION RESULT will be appended below after startup checks complete.*\n"
        )

        with open(RECENT_CHANGES_FILE, "w", encoding="utf-8") as f:
            f.write(content)

        # Update last-seen hash to current HEAD
        with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
            f.write(current_hash)

        print(
            f"[startup-changes] {len(commits)} new commit(s), {len(changed_files)} file(s) changed "
            f"(critical={touches_critical}) — written to docs/RECENT_CHANGES.md"
        )

        return {
            "found":                True,
            "commit_count":         len(commits),
            "file_count":           len(changed_files),
            "touches_critical_paths": touches_critical,
            "old_hash":             last_hash,
            "new_hash":             current_hash,
            "changed_files":        changed_files,
        }

    except Exception as e:
        print(f"[startup-changes] detect error: {e}")
        return {"found": False, "error": str(e)}


async def run_startup_verification(changed_files: list, touches_critical: bool) -> dict:
    """
    Run lint → tests → liveness on the changed files.
    Appends a VERIFICATION RESULT section to docs/RECENT_CHANGES.md.
    Returns {passed, details, lint, tests, liveness}.

    The liveness check reuses check_backend_liveness() from system_tool — no duplicated
    retry/timeout logic. Called as an async task after FastAPI has started serving.
    """
    import asyncio

    results: dict = {}
    details: list = []

    # 1. Lint changed .py files (skip deleted files — they no longer exist)
    py_files = [
        os.path.join(BASE_DIR, fp)
        for ct, fp in changed_files
        if fp.endswith(".py") and ct != "D"
    ]
    existing_py = [p for p in py_files if os.path.exists(p)]

    if existing_py:
        print(f"[startup-changes] linting {len(existing_py)} changed Python file(s)...")
        try:
            from tools.lint_tool import handle as lint_handle
            lint_result = await asyncio.to_thread(
                lint_handle, "lint_files", {"paths": existing_py}
            )
            lint_output = str(lint_result)
            # "flake8: clean" → no issues. "not installed" → skip, not a failure.
            lint_ok = "flake8: clean" in lint_output or "not installed" in lint_output.lower()
            results["lint"] = {"ok": lint_ok, "output": lint_output[:1000]}
            details.append(f"Lint: {'PASS' if lint_ok else 'FAIL'}")
        except Exception as e:
            results["lint"] = {"ok": False, "output": str(e)}
            lint_ok = False
            details.append(f"Lint: ERROR — {e}")
    else:
        lint_ok = True
        results["lint"] = {"ok": True, "output": "No changed Python files to lint."}
        details.append("Lint: skipped (no .py changes)")

    # 2. Run the test suite (no test files = pass, not fail)
    print("[startup-changes] running test suite...")
    try:
        from tools.test_tool import handle as test_handle
        test_result = await asyncio.to_thread(test_handle, "run_tests", {})
        test_output = str(test_result)
        # "No test files found" → clean pass; "PASSED" → clean pass
        tests_ok = (
            "no test files found" in test_output.lower()
            or "passed" in test_output.lower()
        )
        results["tests"] = {"ok": tests_ok, "output": test_output[:1000]}
        details.append(f"Tests: {'PASS' if tests_ok else 'FAIL'}")
    except Exception as e:
        results["tests"] = {"ok": False, "output": str(e)}
        tests_ok = False
        details.append(f"Tests: ERROR — {e}")

    # 3. Liveness check — reuse check_backend_liveness() from system_tool (Fix 2)
    print("[startup-changes] checking backend liveness...")
    try:
        from tools.system_tool import check_backend_liveness
        liveness_ok, liveness_msg = await asyncio.to_thread(check_backend_liveness)
        results["liveness"] = {"ok": liveness_ok, "output": liveness_msg}
        details.append(f"Backend liveness: {'PASS' if liveness_ok else 'FAIL'}")
    except Exception as e:
        liveness_ok = False
        liveness_msg = str(e)
        results["liveness"] = {"ok": False, "output": liveness_msg}
        details.append(f"Backend liveness: ERROR — {e}")

    passed = lint_ok and tests_ok and liveness_ok

    # Append verification result to RECENT_CHANGES.md
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        verdict = "ALL CHECKS PASSED ✓" if passed else "ONE OR MORE CHECKS FAILED ✗"

        rows = [
            f"| Lint | {'PASS' if lint_ok else 'FAIL'} |",
            f"| Tests | {'PASS' if tests_ok else 'FAIL'} |",
            f"| Backend liveness | {'PASS' if liveness_ok else 'FAIL'} |",
        ]

        extra = []
        if not lint_ok and results.get("lint", {}).get("output"):
            extra.append(f"### Lint output\n```\n{results['lint']['output']}\n```\n")
        if not tests_ok and results.get("tests", {}).get("output"):
            extra.append(f"### Test output\n```\n{results['tests']['output']}\n```\n")
        if not liveness_ok:
            extra.append(f"### Liveness detail\n{liveness_msg}\n")

        section = (
            f"\n## VERIFICATION RESULT — {now_str}\n\n"
            f"**Overall: {verdict}**\n\n"
            f"| Check | Result |\n"
            f"|-------|--------|\n"
            + "\n".join(rows)
            + ("\n\n" + "\n".join(extra) if extra else "\n")
        )

        if os.path.exists(RECENT_CHANGES_FILE):
            with open(RECENT_CHANGES_FILE, "a", encoding="utf-8") as f:
                f.write(section)
    except Exception as e:
        print(f"[startup-changes] could not append verification result: {e}")

    return {"passed": passed, "details": details, **results}
