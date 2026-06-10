"""TINA Tool — Obsidian Vault (search + read)"""
import os
import re
from pathlib import Path

# Import vault root from config if available, else fall back to default
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import VAULT_DIR
    VAULT_ROOT = Path(VAULT_DIR)
except Exception:
    VAULT_ROOT = Path(r"C:\Users\nrlocal\Desktop\KLJ\Memory")

DEFINITIONS = [
    {
        "name": "vault_search",
        "description": (
            "Search Kai's Obsidian knowledge vault — past conversations, stored facts, "
            "preferences, project notes, and anything previously remembered. "
            "Use when asked about previous discussions, to recall stored knowledge, "
            "or when memory context would improve the response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or phrase to search for.",
                },
                "folder": {
                    "type": "string",
                    "description": "Optional subfolder to limit search, e.g. '02-Tina-Memory' or '03-Chat-Archives'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "vault_read",
        "description": "Read a specific note from the vault by filename. Use after vault_search identifies a relevant note.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Note filename e.g. '2026-06-10-kai-preferences.md'",
                },
                "folder": {
                    "type": "string",
                    "description": "Subfolder path relative to vault root e.g. '02-Tina-Memory/Learned'",
                },
            },
            "required": ["filename"],
        },
    },
]


def _search(query: str, folder: str | None) -> str:
    root = VAULT_ROOT / folder if folder else VAULT_ROOT
    if not root.exists():
        return f"Folder not found: {root}"

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []

    for md in sorted(root.rglob("*.md"))[:500]:  # cap at 500 files for speed
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                # Return up to 3 matching lines with context
                lines   = text.splitlines()
                matches = [
                    f"  line {i+1}: {line.strip()}"
                    for i, line in enumerate(lines)
                    if pattern.search(line)
                ][:3]
                rel = md.relative_to(VAULT_ROOT)
                results.append(f"[[{md.stem}]] ({rel})\n" + "\n".join(matches))
        except Exception:
            continue

    if not results:
        return f"No vault notes found matching '{query}'."
    header = f"Found {len(results)} note(s) matching '{query}':\n\n"
    return header + "\n\n".join(results[:15])  # return top 15 matches


def _read(filename: str, folder: str | None) -> str:
    if folder:
        path = VAULT_ROOT / folder / filename
    else:
        # Search for the file anywhere in vault
        matches = list(VAULT_ROOT.rglob(filename))
        if not matches:
            return f"Note not found: {filename}"
        path = matches[0]

    if not path.exists():
        return f"Note not found: {path}"

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Truncate very long notes
        if len(content) > 6000:
            content = content[:6000] + "\n\n[... truncated ...]"
        return content
    except Exception as e:
        return f"Could not read note: {e}"


def handle(name: str, inputs: dict) -> str:
    if name == "vault_search":
        return _search(inputs.get("query", ""), inputs.get("folder"))
    if name == "vault_read":
        return _read(inputs.get("filename", ""), inputs.get("folder"))
    return f"Unknown vault tool: {name}"
