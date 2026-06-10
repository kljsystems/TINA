"""
Filesystem tool — gives agents read/write access to the local machine.
All writes are logged to stdout for audit visibility.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECTS

DEFINITIONS = [
    {
        "name":        "fs_list_projects",
        "description": "Return all registered projects and their local filesystem paths. Call this first whenever working on a named project.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name":        "fs_list",
        "description": "List the contents of a directory. Returns files and subdirectories. Use to explore project structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the directory."},
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
        path = inputs.get("path", "")
        try:
            if not os.path.exists(path):
                return f"Path does not exist: {path}"
            if not os.path.isdir(path):
                return f"Not a directory: {path}"
            entries = sorted(os.listdir(path))
            lines   = [e + ("/" if os.path.isdir(os.path.join(path, e)) else "") for e in entries]
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
