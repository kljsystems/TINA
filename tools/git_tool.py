import os
import sys
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFINITIONS = [
    {
        "name": "git_status",
        "description": "Show working tree status for a project — staged, unstaged, and untracked files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
            },
            "required": ["project_path"],
        },
    },
    {
        "name": "git_diff",
        "description": "Show uncommitted changes. Pass a file path to diff a specific file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "file_path":    {"type": "string", "description": "Optional: specific file to diff."},
                "staged":       {"type": "boolean", "description": "If true, show staged diff (default false)."},
            },
            "required": ["project_path"],
        },
    },
    {
        "name": "git_log",
        "description": "Show recent commit history for a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "count":        {"type": "integer", "description": "Number of commits to show (default 10)."},
            },
            "required": ["project_path"],
        },
    },
    {
        "name": "git_add",
        "description": (
            "Stage specific files for commit. Always stage by explicit file path — "
            "never use '.' or '-A' to avoid accidentally staging .env or credentials."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "files": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "description": "List of file paths to stage (relative to project root).",
                },
            },
            "required": ["project_path", "files"],
        },
    },
    {
        "name": "git_commit",
        "description": "Commit staged changes with a message. Runs git status first to confirm something is staged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "message":      {"type": "string", "description": "Commit message. Be descriptive — include what changed and why."},
            },
            "required": ["project_path", "message"],
        },
    },
    {
        "name": "git_branch",
        "description": "List branches or create a new one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "create":       {"type": "string", "description": "Branch name to create and switch to. Omit to just list branches."},
            },
            "required": ["project_path"],
        },
    },
    {
        "name": "git_checkout",
        "description": "Switch to an existing branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
                "branch":       {"type": "string", "description": "Branch name to switch to."},
            },
            "required": ["project_path", "branch"],
        },
    },
    {
        "name": "git_push",
        "description": (
            "Push the current branch to the remote. "
            "Refused on main/master — Sam must push to a feature branch only. "
            "Never force-pushes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Absolute path to the git repo root."},
            },
            "required": ["project_path"],
        },
    },
]


def handle(name: str, inputs: dict) -> str:
    path = inputs.get("project_path", "")
    if not os.path.isdir(path):
        return f"Project path not found: {path!r}"

    if name == "git_status":
        return _run(["git", "status", "--short", "--branch"], path)

    if name == "git_diff":
        cmd = ["git", "diff"]
        if inputs.get("staged"):
            cmd.append("--staged")
        if inputs.get("file_path"):
            cmd.append(inputs["file_path"])
        out = _run(cmd, path)
        return out or "No changes."

    if name == "git_log":
        count = min(int(inputs.get("count", 10)), 50)
        return _run(
            ["git", "log", f"-{count}", "--oneline", "--decorate"],
            path,
        )

    if name == "git_add":
        files = inputs.get("files", [])
        if not files:
            return "No files specified. Pass an explicit list of file paths to stage."
        # Safety: refuse to stage sensitive files
        blocked = [f for f in files if os.path.basename(f) in (".env", "credentials.json", "token.json")]
        if blocked:
            return f"Refused to stage sensitive files: {blocked}"
        return _run(["git", "add", "--"] + files, path)

    if name == "git_commit":
        msg = inputs.get("message", "").strip()
        if not msg:
            return "Commit message is required."
        # Check something is actually staged
        staged = _run(["git", "diff", "--staged", "--name-only"], path).strip()
        if not staged:
            return "Nothing staged. Call git_add first."
        return _run(["git", "commit", "-m", msg], path)

    if name == "git_branch":
        create = inputs.get("create", "").strip()
        if create:
            return _run(["git", "checkout", "-b", create], path)
        return _run(["git", "branch", "-a"], path)

    if name == "git_checkout":
        branch = inputs.get("branch", "").strip()
        if not branch:
            return "Branch name required."
        return _run(["git", "checkout", branch], path)

    if name == "git_push":
        # Refuse pushes directly to main/master
        current = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).strip()
        if current in ("main", "master"):
            return (
                f"Refused: currently on {current!r}. "
                "Create a feature branch first with git_branch, then push from there."
            )
        return _run(["git", "push", "-u", "origin", current], path)

    return f"Unknown tool: {name}"


def _run(cmd: list[str], cwd: str) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (result.stdout + result.stderr).strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return f"git command timed out: {' '.join(cmd)}"
    except FileNotFoundError:
        return "git is not installed or not on PATH."
    except Exception as e:
        return f"git error: {e}"
