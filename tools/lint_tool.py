"""Linter tool — runs flake8 and optional mypy on files Sam writes."""
import os
import sys
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFINITIONS = [
    {
        "name": "lint_files",
        "description": (
            "Run flake8 (style + syntax errors) and optionally mypy (type errors) on one or more Python files. "
            "Call this after writing or editing Python files, before restarting the backend or committing. "
            "Returns errors and warnings grouped by file. Clean output means the files are safe to run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "Absolute paths of Python files to lint.",
                },
                "mypy": {
                    "type":        "boolean",
                    "description": "Also run mypy type checking (default false — slower but catches type errors).",
                },
            },
            "required": ["paths"],
        },
    },
]


def handle(name: str, inputs: dict) -> str:
    if name == "lint_files":
        return _lint(
            paths=inputs.get("paths", []),
            run_mypy=inputs.get("mypy", False),
        )
    return f"Unknown tool: {name}"


def _lint(paths: list[str], run_mypy: bool = False) -> str:
    if not paths:
        return "No file paths provided."

    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        return f"Files not found: {missing}"

    results = []

    # flake8 — syntax errors, undefined names, style issues
    try:
        r = subprocess.run(
            [sys.executable, "-m", "flake8",
             "--max-line-length=120",
             "--extend-ignore=E501,W503",  # ignore long lines and line-break style
             "--"] + paths,
            capture_output=True, text=True, timeout=30,
        )
        out = (r.stdout + r.stderr).strip()
        if out:
            results.append(f"flake8:\n{out}")
        else:
            results.append("flake8: clean")
    except FileNotFoundError:
        results.append("flake8: not installed (pip install flake8)")
    except subprocess.TimeoutExpired:
        results.append("flake8: timed out")

    # mypy — optional type checking
    if run_mypy:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "mypy",
                 "--ignore-missing-imports",
                 "--no-error-summary",
                 "--"] + paths,
                capture_output=True, text=True, timeout=60,
            )
            out = (r.stdout + r.stderr).strip()
            if out:
                results.append(f"mypy:\n{out}")
            else:
                results.append("mypy: clean")
        except FileNotFoundError:
            results.append("mypy: not installed (pip install mypy)")
        except subprocess.TimeoutExpired:
            results.append("mypy: timed out")

    return "\n\n".join(results)
