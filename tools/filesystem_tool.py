"""
Filesystem tool — gives agents read/write access to the local machine.
All writes are logged to stdout for audit visibility.
"""

import os
import sys
import queue
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECTS

# Written files are pushed here; main.py drains this and broadcasts code_preview events
_preview_queue: "queue.Queue[dict]" = queue.Queue()

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
        "description": (
            "Read the contents of a file. Returns up to 10 000 chars by default. "
            "For large files, use offset and limit to read in chunks. "
            "offset is the line number to start from (1-indexed). "
            "limit is the maximum number of lines to return (default: all remaining up to 10 000 chars). "
            "The response tells you how many lines the file has so you know whether to read more chunks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":   {"type": "string",  "description": "Absolute path to the file."},
                "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed). Default: 1."},
                "limit":  {"type": "integer", "description": "Maximum number of lines to read. Default: all remaining."},
            },
            "required": ["path"],
        },
    },
    {
        "name":        "fs_patch",
        "description": (
            "Make a targeted edit to a file by replacing an exact string. "
            "old_string must appear exactly once in the file — provide enough surrounding context to make it unique. "
            "Use this instead of fs_write when you only need to change part of a file. "
            "Set replace_all=true to replace every occurrence (useful for renaming a variable throughout a file)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Absolute path to the file to edit."},
                "old_string":  {"type": "string",  "description": "Exact string to find and replace. Must be unique in the file unless replace_all is true."},
                "new_string":  {"type": "string",  "description": "String to replace it with."},
                "replace_all": {"type": "boolean", "description": "If true, replace every occurrence. Default: false (errors if not unique)."},
            },
            "required": ["path", "old_string", "new_string"],
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
        path   = inputs.get("path", "")
        offset = max(1, int(inputs.get("offset", 1)))
        limit  = inputs.get("limit", None)
        try:
            if not os.path.exists(path):
                return f"File not found: {path}"
            if os.path.isdir(path):
                return f"That's a directory — use fs_list instead: {path}"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            total = len(all_lines)
            start = offset - 1  # convert to 0-indexed
            chunk = all_lines[start:start + limit] if limit else all_lines[start:]
            # Cap at 10 000 chars to avoid overwhelming the model context
            text = "".join(chunk)
            end_line = start + len(chunk)
            header = f"[Lines {offset}–{end_line} of {total}]\n"
            if len(text) > 10_000:
                # Trim to char limit and recalculate end line
                text = text[:10_000]
                trimmed_lines = text.count("\n")
                end_line = start + trimmed_lines
                header = f"[Lines {offset}–{end_line} of {total} — char limit reached]\n"
                suffix = f"\n\n...(truncated at 10 000 chars — use offset={end_line + 1} to continue)"
                return header + text + suffix
            return header + text
        except Exception as e:
            return f"Error reading {path}: {e}"

    if name == "fs_patch":
        path        = inputs.get("path", "")
        old_string  = inputs.get("old_string", "")
        new_string  = inputs.get("new_string", "")
        replace_all = inputs.get("replace_all", False)
        try:
            if not os.path.exists(path):
                return f"File not found: {path}"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            count = content.count(old_string)
            if count == 0:
                return f"old_string not found in {path} — check the exact text and whitespace."
            if not replace_all and count > 1:
                return (
                    f"old_string appears {count} times in {path}. "
                    "Provide more surrounding context to make it unique, or set replace_all=true."
                )
            updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            replaced = count if replace_all else 1
            print(f"[fs_patch] {path} — replaced {replaced} occurrence(s)")
            _preview_queue.put_nowait({"path": path, "content": updated})
            return f"Patched: {path} ({replaced} replacement(s))"
        except Exception as e:
            return f"Error patching {path}: {e}"

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
            _preview_queue.put_nowait({"path": path, "content": content})
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
