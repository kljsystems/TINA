"""Background memory writer — fires after every response, non-blocking.
Writes structured, heavily-linked Obsidian notes to grow the knowledge graph.
"""
import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import ANTHROPIC_API_KEY, ORCHESTRATOR_MODEL, VAULT_DIR, PROJECTS

import anthropic

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
_VAULT  = Path(VAULT_DIR)

# Known hub notes — every relevant note should link to these
_HUB_NOTES = {
    "ky":       "00-You/USER",
    "tina":     "01-Projects/tina/CLAUDE",
    "sam":      "01-Projects/tina/CLAUDE",
    "research": "01-Projects/tina/CLAUDE",
}

# Note type → vault folder
_FOLDERS = {
    "fact":     "02-Tina-Memory/Learned",
    "decision": "02-Tina-Memory/Decisions",
    "person":   "02-Tina-Memory/People",
    "project":  None,  # resolved dynamically to 01-Projects/{name}/Notes
}

_SYSTEM = """You are TINA's memory core. After each conversation turn, extract knowledge worth keeping as Obsidian notes.

VAULT STRUCTURE:
- 02-Tina-Memory/Learned/     — facts, preferences, patterns about Ky and how he works
- 02-Tina-Memory/Decisions/   — decisions made, why, what was rejected
- 02-Tina-Memory/People/      — notes about people Ky mentions (colleagues, clients, etc.)
- 01-Projects/{name}/Notes/   — project-specific technical notes, discoveries, context

KNOWN HUB NOTES (always link to these when relevant):
- [[00-You/USER]] — Ky's profile
- [[01-Projects/tina/CLAUDE]] — Tina system context
- [[01-Projects/kaos/CLAUDE]] — KAOS project context
(Link to any other project CLAUDE file if that project is discussed)

LINKING RULES — this is critical for the knowledge graph:
- Link EVERYTHING meaningful: people, projects, agents, tools, concepts, decisions
- Every note must have at least 3 [[wikilinks]]
- Use [[note-name|display text]] when the filename differs from natural text
- Link agent names: [[01-Projects/tina/CLAUDE|Sam]], [[01-Projects/tina/CLAUDE|Tina]]
- Link Ky every time he's the subject: [[00-You/USER|Ky]]
- Link project names to their CLAUDE file: [[01-Projects/kaos/CLAUDE|KAOS]]
- Link between related concepts — if this note is about a decision, link to related fact notes
- Create links to notes that don't exist yet — they'll become future notes (shown as red in Obsidian)
- The more links, the better the graph. Be aggressive.

NOTE TYPES:
- "fact"     → things Ky told you, preferences, skills, opinions, patterns
- "decision" → choices made in this conversation, what was decided and why, what was rejected
- "person"   → a person Ky mentioned — their role, relationship to Ky, context
- "project"  → technical context, architecture decisions, discoveries specific to a project

OUTPUT FORMAT — return ONLY a JSON array:
[
  {
    "type": "fact|decision|person|project",
    "project": "kaos",  // only for type=project — must match a known project name
    "filename": "2026-06-10-short-slug.md",
    "content": "---\\ndate: 2026-06-10\\ntags: [tina-memory, decision, kaos]\\n---\\n# Title\\n\\nContent with [[wikilinks]] everywhere.\\n\\n*Written by Tina · 14:32*"
  }
]

FRONTMATTER: date + tags array only. Tags should include: tina-memory, the note type, and any project names.
FILENAME: YYYY-MM-DD-short-slug.md (lowercase, hyphens)
LENGTH: under 250 words per note. Dense and linked, not verbose.

Skip the whole turn if nothing meaningful happened (greetings, one-word replies, simple lookups with no lasting value).
If something is worth remembering, write it. If a decision was made, write it. If something interesting about Ky came up, write it.
Return [] if nothing worth keeping."""


async def extract_and_write_notes(user_msg: str, tina_reply: str) -> None:
    """Extract knowledge from a conversation turn and write linked notes to vault. Never raises."""
    try:
        now   = datetime.now()
        today = now.strftime("%Y-%m-%d")
        time  = now.strftime("%H:%M")

        # Build context about known projects for the LLM
        project_list = ", ".join(PROJECTS.keys())
        project_hubs = "\n".join(
            f"- [[01-Projects/{name}/CLAUDE]] — {name.upper()} project"
            for name in PROJECTS
        )

        system = _SYSTEM.replace(
            "(Link to any other project CLAUDE file if that project is discussed)",
            f"(Link to any other project CLAUDE file if that project is discussed)\n\nKNOWN PROJECTS: {project_list}\n{project_hubs}"
        )

        response = await _client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": (
                f"Date: {today}  Time: {time}\n\n"
                f"Ky said: {user_msg}\n\n"
                f"Tina replied: {tina_reply}"
            )}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$',     '', raw)

        notes = json.loads(raw)
        if not isinstance(notes, list) or not notes:
            return

        for note in notes:
            _write_note(note, today, time)

    except Exception:
        pass  # background task — never surface errors to user


def _write_note(note: dict, today: str, time: str) -> None:
    note_type = note.get("type", "fact")
    filename  = note.get("filename", "")
    content   = note.get("content", "").strip()
    project   = note.get("project", "")

    if not filename or not content:
        return

    # Resolve folder
    if note_type == "project" and project and project in PROJECTS:
        folder = _VAULT / "01-Projects" / project / "Notes"
    elif note_type == "decision":
        folder = _VAULT / "02-Tina-Memory" / "Decisions"
    elif note_type == "person":
        folder = _VAULT / "02-Tina-Memory" / "People"
    else:
        folder = _VAULT / "02-Tina-Memory" / "Learned"

    folder.mkdir(parents=True, exist_ok=True)

    if "*Written by Tina" not in content:
        content += f"\n\n*Written by Tina · {time}*"

    filepath = folder / filename
    if not filepath.exists():
        filepath.write_text(content, encoding="utf-8")
