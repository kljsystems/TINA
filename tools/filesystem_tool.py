"""
Filesystem tool — gives agents read/write access to the local machine.
All writes are logged to stdout for audit visibility.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECTS

# Directories that are never useful to list or read — always skipped
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", ".cache", ".parcel-cache",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "data",  # runtime data, not source code
}

DEFINITIONS = [
    {
        "name":        "fs_list_projects",
        "description": "Return all registered projects and their local filesystem paths. Call this first whenever working on a named project.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name":        "fs_list",
        "description": (
            "List the contents of a directory. node_modules, .git, __pycache__, venv, dist, build, "
            "and other noise directories are always excluded. "
            "Set recursive=true to get the full file tree in one call — use this for codebase indexing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Absolute path to the directory."},
                "recursive": {"type": "boolean", "description": "If true, return full recursive file tree (noise dirs excluded). Default false."},
            },
            "required": ["path"],
        },
    },
    {
        "name":        "fs_read",
        "description": "Read the contents of a file. Large files are truncated at 10 000 chars.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file."},
            },
            "required": ["path"],
        },
    },
    {
        "name":        "fs_write",
        "description": "Write content to a file. Creates the file and any missing parent directories. Overwrites if the file already exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Absolute path to write to."},
                "content": {"type": "string", "description": "Full file content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name":        "fs_mkdir",
        "description": "Create a directory and any missing parent directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path of the directory to create."},
            },
            "required": ["path"],
        },
    },
]


def handle(name: str, inputs: dict) -> str:
    if name == "fs_list_projects":
        if not PROJECTS:
            return "No projects registered."
        return "\n".join(f"{k}: {v}" for k, v in PROJECTS.items())

    if name == "fs_list":
        path      = inputs.get("path", "")
        recursive = inputs.get("recursive", False)
        try:
            if not os.path.exists(path):
                return f"Path does not exist: {path}"
            if not os.path.isdir(path):
                return f"Not a directory: {path}"
            if recursive:
                lines = []
                for dirpath, dirnames, filenames in os.walk(path):
                    # Prune noise dirs in-place so os.walk doesn't descend into them
                    dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
                    rel = os.path.relpath(dirpath, path)
                    prefix = "" if rel == "." else rel + os.sep
                    for fname in sorted(filenames):
                        lines.append(prefix + fname)
                return "\n".join(lines) if lines else "(empty)"
            else:
                entries = sorted(os.listdir(path))
                lines   = []
                for e in entries:
                    full = os.path.join(path, e)
                    if os.path.isdir(full):
                        lines.append(e + ("/" if e not in _SKIP_DIRS else "/  [skipped]"))
                    else:
                        lines.append(e)
                return "\n".join(lines) if lines else "(empty directory)"
        except Exception as e:
            return f"Error listing {path}: {e}"

    if name == "fs_read":
        path = inputs.get("path", "")
        try:
            if not os.path.exists(path):
                return f"File not found: {path}"
            if os.path.isdir(path):
                return f"That's a directory — use fs_list instead: {path}"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) > 10_000:
                return content[:10_000] + f"\n\n...(truncated — {len(content):,} chars total, read the rest in chunks)"
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"

    if name == "fs_write":
        path    = inputs.get("path", "")
        content = inputs.get("content", "")
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[fs_write] {path} ({len(content):,} chars)")
            return f"Written: {path} ({len(content):,} chars)"
        except Exception as e:
            return f"Error writing {path}: {e}"

    if name == "fs_mkdir":
        path = inputs.get("path", "")
        try:
            os.makedirs(path, exist_ok=True)
            return f"Directory ready: {path}"
        except Exception as e:
            return f"Error creating {path}: {e}"

    return f"Unknown filesystem tool: {name}"
