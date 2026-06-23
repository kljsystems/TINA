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
        "name": "vault_write",
        "description": (
            "Create a new note in the vault. Every agent uses this to build persistent memory. "
            "Write after completing any non-trivial task — capture what was done, decisions made, "
            "contacts encountered, findings, anomalies, or anything worth knowing next time. "
            "The vault grows with every task. Write in Obsidian markdown with [[wikilinks]]. "
            "Each agent has their own folder: 02-Tina-Memory/Agents/{AgentName}/. "
            "Returns an error if the file already exists — use vault_append to add to an existing note."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type":        "string",
                    "description": "Subfolder relative to vault root, e.g. '02-Tina-Memory/Agents/Sam' or '02-Tina-Memory/Decisions'",
                },
                "filename": {
                    "type":        "string",
                    "description": "Note filename, e.g. '2026-06-23-tina-auth-refactor.md' or 'john-smith.md'",
                },
                "content": {
                    "type":        "string",
                    "description": "Full note in Obsidian markdown. Include frontmatter (tags, date) and [[wikilinks]] to related notes.",
                },
            },
            "required": ["folder", "filename", "content"],
        },
    },
    {
        "name": "vault_append",
        "description": (
            "Append content to an existing vault note. Creates the note if it doesn't exist yet. "
            "Use for ongoing records that grow over time: contact profiles (each email interaction adds a log entry), "
            "project notes (each coding session adds what changed), data history (each analysis adds new metrics). "
            "This is the right tool when the note already exists and you want to add to it rather than create a new file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type":        "string",
                    "description": "Subfolder relative to vault root, e.g. '02-Tina-Memory/Agents/Tristan'",
                },
                "filename": {
                    "type":        "string",
                    "description": "Note filename to append to, e.g. 'john-smith.md'",
                },
                "content": {
                    "type":        "string",
                    "description": "Content to append. Will be added after existing content with a blank line separator.",
                },
            },
            "required": ["folder", "filename", "content"],
        },
    },
    {
        "name": "vault_list",
        "description": (
            "List all notes in a vault folder. Use before vault_write to check whether a note already exists "
            "(e.g. to see if a contact profile is there before creating one), or to browse what's been captured "
            "in your agent folder. Returns filenames only — use vault_read to see the content of a specific note."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type":        "string",
                    "description": "Subfolder relative to vault root, e.g. '02-Tina-Memory/Agents/Charlie'",
                },
            },
            "required": ["folder"],
        },
    },
    {
        "name": "vault_search",
        "description": (
            "Search the entire Obsidian vault — past research, contact notes, project decisions, "
            "data insights, coding history, and anything any agent has written. "
            "Always call this before starting a task — prior work may already exist. "
            "Use specific queries: a person's name, a project name, a topic, a company name."
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
                    "description": "Optional subfolder to limit search, e.g. '02-Tina-Memory/Agents/Charlie' or '02-Tina-Memory/People'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "vault_read",
        "description": "Read a specific note from the vault by filename. Use after vault_search or vault_list identifies a relevant note.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Note filename e.g. 'john-smith.md' or '2026-06-23-tina-auth.md'",
                },
                "folder": {
                    "type": "string",
                    "description": "Subfolder path relative to vault root e.g. '02-Tina-Memory/Agents/Tristan'",
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


def _write(folder: str, filename: str, content: str) -> str:
    path = VAULT_ROOT / folder / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return f"Note already exists: {path.relative_to(VAULT_ROOT)} — use vault_append to add to it."
        path.write_text(content, encoding="utf-8")
        return f"Written: {path.relative_to(VAULT_ROOT)}"
    except Exception as e:
        return f"Could not write note: {e}"


def _append(folder: str, filename: str, content: str) -> str:
    path = VAULT_ROOT / folder / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + "\n\n" + content, encoding="utf-8")
            return f"Appended to: {path.relative_to(VAULT_ROOT)}"
        else:
            path.write_text(content, encoding="utf-8")
            return f"Created: {path.relative_to(VAULT_ROOT)}"
    except Exception as e:
        return f"Could not append to note: {e}"


def _list(folder: str) -> str:
    root = VAULT_ROOT / folder if folder else VAULT_ROOT
    if not root.exists():
        return f"Folder not found: {root}"
    files = sorted(f.name for f in root.iterdir() if f.is_file() and f.suffix == ".md")
    if not files:
        return f"No notes in {folder}."
    return f"{len(files)} note(s) in {folder}:\n" + "\n".join(f"- {f}" for f in files)


def handle(name: str, inputs: dict) -> str:
    if name == "vault_write":
        return _write(inputs.get("folder", ""), inputs.get("filename", ""), inputs.get("content", ""))
    if name == "vault_append":
        return _append(inputs.get("folder", ""), inputs.get("filename", ""), inputs.get("content", ""))
    if name == "vault_list":
        return _list(inputs.get("folder", ""))
    if name == "vault_search":
        return _search(inputs.get("query", ""), inputs.get("folder"))
    if name == "vault_read":
        return _read(inputs.get("filename", ""), inputs.get("folder"))
    return f"Unknown vault tool: {name}"
