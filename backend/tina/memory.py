"""Background memory writer — fires after every response, non-blocking."""
import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import ANTHROPIC_API_KEY, ORCHESTRATOR_MODEL, VAULT_DIR

import anthropic

_client    = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
_VAULT     = Path(VAULT_DIR)
_LEARN_DIR = _VAULT / "02-Tina-Memory" / "Learned"

_SYSTEM = """You are TINA's memory core. After each conversation turn, extract knowledge worth keeping.

Write 1-3 Obsidian notes. Each note covers exactly ONE topic.

Write notes about:
- Facts about Kai (preferences, habits, skills, background, opinions)
- Decisions made and why
- Project context or technical details worth retaining
- Patterns in how Kai works or thinks
- Anything that would be useful to recall in a future conversation

Skip if the turn contains nothing meaningful to remember (e.g. simple greetings, one-word replies).

Rules:
- Obsidian frontmatter required: date, tags array, no extra fields
- Use [[wikilinks]] for any references to other vault notes or topics
- Internal vault links ONLY use [[wikilinks]] — never standard markdown links
- Neutral, precise tone. Facts not vibes.
- Keep each note under 200 words
- Filename: YYYY-MM-DD-short-slug.md (lowercase, hyphens, no spaces)
- Folder: always "02-Tina-Memory/Learned"

Return ONLY a JSON array — no markdown, no explanation:
[
  {
    "filename": "2026-06-10-kai-prefers-python.md",
    "content": "---\\ndate: 2026-06-10\\ntags: [tina-memory, learned, preferences]\\n---\\n# Kai Prefers Python for Backend\\n\\nContent here.\\n\\n*Written by Tina · 14:32*"
  }
]

If nothing is worth remembering, return an empty array: []"""


def _safe_slug(text: str, max_len: int = 40) -> str:
    text = re.sub(r'[^a-z0-9\s-]', '', text.lower())
    text = re.sub(r'\s+', '-', text.strip())
    return text[:max_len].rstrip('-')


async def extract_and_write_notes(user_msg: str, tina_reply: str) -> None:
    """Extract knowledge from a conversation turn and write to vault. Never raises."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        time  = datetime.now().strftime("%H:%M")

        prompt = (
            f"Date: {today}\n\n"
            f"Kai said: {user_msg}\n\n"
            f"Tina replied: {tina_reply}"
        )

        response = await _client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        notes = json.loads(raw)
        if not isinstance(notes, list) or not notes:
            return

        _LEARN_DIR.mkdir(parents=True, exist_ok=True)

        for note in notes:
            filename = note.get("filename", "")
            content  = note.get("content", "").strip()
            if not filename or not content:
                continue

            # Ensure timestamp is injected if not already present
            if f"*Written by Tina" not in content:
                content += f"\n\n*Written by Tina · {time}*"

            filepath = _LEARN_DIR / filename
            if not filepath.exists():
                filepath.write_text(content, encoding="utf-8")

    except Exception:
        pass  # background task — never surface errors to user
