"""
Import Claude.ai chat export into Obsidian vault with wikilinks.

Usage:
    python scripts/import_claude_chats.py <export.zip or conversations.json>

How to get your export:
    1. Go to claude.ai → Settings → Privacy → Export Data
    2. Wait for the email, download the ZIP
    3. Run this script pointing at the ZIP or extracted conversations.json

Creates:
    Memory/03-Chat-Archives/YYYY-MM-DD-<title>.md  — one note per conversation
    Memory/03-Chat-Archives/00-Chat-Index.md        — master index with all links
"""

import json
import zipfile
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

VAULT_DIR  = Path(r"C:\Users\nrlocal\Desktop\KLJ\Memory")
OUTPUT_DIR = VAULT_DIR / "03-Chat-Archives"


def safe_filename(title: str, max_len: int = 60) -> str:
    title = re.sub(r'[<>:"/\\|?*\n\r]', '', title).strip()
    return title[:max_len] or "Untitled"


def parse_date(iso: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return "0000-00-00", ""


def note_stem(conv: dict) -> str:
    """Return the filename stem (no .md) for a conversation."""
    date, _ = parse_date(conv.get("created_at", ""))
    title   = safe_filename(conv.get("name") or "Untitled")
    return f"{date}-{title}"


def format_note(conv: dict, prev_stem: str | None, next_stem: str | None) -> str:
    title    = conv.get("name") or "Untitled"
    created  = conv.get("created_at", "")
    date, _  = parse_date(created)
    messages = conv.get("chat_messages", [])

    # Build nav arrows
    prev_link = f"[[{prev_stem}|← prev]]" if prev_stem else "—"
    next_link = f"[[{next_stem}|next →]]" if next_stem else "—"

    lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"date: {date}",
        "tags: [claude-chat, chat-archive]",
        f"prev: \"[[{prev_stem}]]\"" if prev_stem else "prev: null",
        f"next: \"[[{next_stem}]]\"" if next_stem else "next: null",
        "---",
        "",
        f"# {title}",
        "",
        f"*{date} · {len(messages)} messages · {prev_link} · {next_link} · [[00-Chat-Index|index]]*",
        "",
        "---",
        "",
    ]

    for msg in messages:
        sender  = msg.get("sender", "unknown")
        text    = (msg.get("text") or "").strip()
        ts_raw  = msg.get("created_at", "")
        _, time = parse_date(ts_raw)

        label = f"**{'Kai' if sender == 'human' else 'Claude'}**"
        if time:
            label += f" · {time}"

        lines += [f"### {label}", "", text, "", "---", ""]

    # Footer nav
    lines += [
        "",
        f"*{prev_link} · [[00-Chat-Index|index]] · {next_link}*",
    ]

    return "\n".join(lines)


def format_index(ordered: list[dict]) -> str:
    """Build a master index note grouped by month."""
    lines = [
        "---",
        "title: Claude Chat Index",
        "date: " + datetime.now().strftime("%Y-%m-%d"),
        "tags: [claude-chat, index]",
        "---",
        "",
        "# Claude Chat Archive",
        "",
        f"*{len(ordered)} conversations imported from Claude.ai*",
        "",
        "---",
        "",
    ]

    by_month: dict[str, list[dict]] = defaultdict(list)
    for conv in ordered:
        date, _ = parse_date(conv.get("created_at", ""))
        month   = date[:7]  # YYYY-MM
        by_month[month].append(conv)

    for month in sorted(by_month.keys(), reverse=True):
        try:
            heading = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        except Exception:
            heading = month
        lines += [f"## {heading}", ""]
        for conv in by_month[month]:
            stem  = note_stem(conv)
            title = conv.get("name") or "Untitled"
            date, time = parse_date(conv.get("created_at", ""))
            count = len(conv.get("chat_messages", []))
            lines.append(f"- [[{stem}|{title}]] · {date} · {count} messages")
        lines.append("")

    return "\n".join(lines)


def load_conversations(path: Path) -> list[dict]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            names  = zf.namelist()
            target = next((n for n in names if n.endswith("conversations.json")), None)
            if not target:
                print(f"No conversations.json in ZIP. Contents: {names}")
                sys.exit(1)
            with zf.open(target) as f:
                data = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    convs = data if isinstance(data, list) else data.get("conversations", [])
    return [c for c in convs if c.get("chat_messages")]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    conversations = load_conversations(input_path)
    print(f"Found {len(conversations)} conversations with messages")

    # Sort chronologically
    conversations.sort(key=lambda c: c.get("created_at", ""))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {OUTPUT_DIR}\n")

    # Pre-compute stems so prev/next links are accurate
    stems = [note_stem(c) for c in conversations]

    written = skipped = 0

    for i, conv in enumerate(conversations):
        stem     = stems[i]
        filepath = OUTPUT_DIR / f"{stem}.md"

        if filepath.exists():
            skipped += 1
            continue

        prev_stem = stems[i - 1] if i > 0 else None
        next_stem = stems[i + 1] if i < len(conversations) - 1 else None

        content = format_note(conv, prev_stem, next_stem)
        filepath.write_text(content, encoding="utf-8")
        written += 1
        if written % 50 == 0:
            print(f"  {written} written...")

    # Always regenerate the index
    index_path = OUTPUT_DIR / "00-Chat-Index.md"
    index_path.write_text(format_index(conversations), encoding="utf-8")
    print(f"  Index updated: 00-Chat-Index.md")

    print(f"\nDone.")
    print(f"  Written:  {written}")
    print(f"  Skipped:  {skipped}  (already exist — re-run with --force to overwrite)")
    print(f"  Index:    {index_path}")
    print(f"\nOpen 00-Chat-Index.md in Obsidian to browse everything.")


if __name__ == "__main__":
    main()
