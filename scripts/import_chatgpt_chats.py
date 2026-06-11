"""
Import ChatGPT chat export into Obsidian vault with wikilinks.

Usage:
    python scripts/import_chatgpt_chats.py <export.zip or conversations.json>

How to get your export:
    1. Go to chatgpt.com → Settings → Data Controls → Export data
    2. Wait for the email, download the ZIP
    3. Run this script pointing at the ZIP or extracted conversations.json

Creates:
    Memory/03-Chat-Archives/chatgpt-YYYY-MM-DD-<title>.md  — one note per conversation
    Memory/03-Chat-Archives/00-ChatGPT-Index.md             — master index with all links
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


def unix_to_parts(ts) -> tuple[str, str]:
    """Convert a Unix timestamp (float or None) to (YYYY-MM-DD, HH:MM)."""
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return "0000-00-00", ""


def extract_text(message: dict) -> str:
    """Pull plain text out of a ChatGPT message content block."""
    content = message.get("content") or {}
    parts   = content.get("parts") or []
    chunks  = []
    for part in parts:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, dict):
            # Image/file attachment — note the type but skip the data
            kind = part.get("content_type", "attachment")
            chunks.append(f"[{kind}]")
    return "\n".join(chunks).strip()


def flatten_messages(mapping: dict) -> list[dict]:
    """
    Walk the message tree and return messages in conversation order.
    ChatGPT stores messages as a tree (to support regenerated responses).
    We follow the main conversation path (deepest chain from root).

    Newer exports omit 'children' arrays — we rebuild them by inverting parent refs.
    """
    if not mapping:
        return []

    # Build children map by inverting parent references
    children_of: dict[str, list[str]] = {nid: [] for nid in mapping}
    for nid, node in mapping.items():
        parent = node.get("parent")
        if parent and parent in children_of:
            children_of[parent].append(nid)

    # Find root: node whose parent is absent or not in mapping
    roots = [nid for nid, node in mapping.items()
             if not node.get("parent") or node["parent"] not in mapping]
    if not roots:
        return []

    # Walk from root following first child at each branch
    messages = []
    current  = roots[0]
    visited  = set()

    while current and current not in visited:
        visited.add(current)
        node = mapping.get(current, {})
        msg  = node.get("message")

        if msg:
            role   = (msg.get("author") or {}).get("role", "")
            text   = extract_text(msg)
            status = msg.get("status", "")

            if role in ("user", "assistant") and text and status != "interrupted":
                messages.append({
                    "role": role,
                    "text": text,
                    "ts":   msg.get("create_time"),
                })

        kids    = node.get("children") or children_of.get(current) or []
        current = kids[0] if kids else None

    return messages


def note_stem(conv: dict) -> str:
    date, _ = unix_to_parts(conv.get("create_time"))
    title   = safe_filename(conv.get("title") or "Untitled")
    return f"chatgpt-{date}-{title}"


def format_note(conv: dict, prev_stem: str | None, next_stem: str | None) -> str:
    title    = conv.get("title") or "Untitled"
    date, _  = unix_to_parts(conv.get("create_time"))
    messages = flatten_messages(conv.get("mapping") or {})

    prev_link = f"[[{prev_stem}|← prev]]" if prev_stem else "—"
    next_link = f"[[{next_stem}|next →]]" if next_stem else "—"

    lines = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"date: {date}",
        "tags: [chatgpt-chat, chat-archive]",
        f"prev: \"[[{prev_stem}]]\"" if prev_stem else "prev: null",
        f"next: \"[[{next_stem}]]\"" if next_stem else "next: null",
        "---",
        "",
        f"# {title}",
        "",
        f"*{date} · {len(messages)} messages · {prev_link} · {next_link} · [[00-ChatGPT-Index|index]]*",
        "",
        "---",
        "",
    ]

    for msg in messages:
        label  = "**Ky**" if msg["role"] == "user" else "**ChatGPT**"
        _, time = unix_to_parts(msg.get("ts"))
        if time:
            label += f" · {time}"

        lines += [f"### {label}", "", msg["text"], "", "---", ""]

    lines += [
        "",
        f"*{prev_link} · [[00-ChatGPT-Index|index]] · {next_link}*",
    ]

    return "\n".join(lines)


def format_index(ordered: list[dict]) -> str:
    lines = [
        "---",
        "title: ChatGPT Chat Index",
        "date: " + datetime.now().strftime("%Y-%m-%d"),
        "tags: [chatgpt-chat, index]",
        "---",
        "",
        "# ChatGPT Chat Archive",
        "",
        f"*{len(ordered)} conversations imported from ChatGPT*",
        "",
        "---",
        "",
    ]

    by_month: dict[str, list[dict]] = defaultdict(list)
    for conv in ordered:
        date, _ = unix_to_parts(conv.get("create_time"))
        by_month[date[:7]].append(conv)

    for month in sorted(by_month.keys(), reverse=True):
        try:
            heading = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        except Exception:
            heading = month
        lines += [f"## {heading}", ""]
        for conv in by_month[month]:
            stem  = note_stem(conv)
            title = conv.get("title") or "Untitled"
            date, _ = unix_to_parts(conv.get("create_time"))
            msgs  = flatten_messages(conv.get("mapping") or {})
            lines.append(f"- [[{stem}|{title}]] · {date} · {len(msgs)} messages")
        lines.append("")

    return "\n".join(lines)


def load_conversations(path: Path) -> list[dict]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            # Support both single conversations.json and split conversations-000.json, -001.json, ...
            targets = sorted(n for n in names if re.search(r'conversations(-\d+)?\.json$', n))
            if not targets:
                print(f"No conversations JSON found in ZIP. Contents: {names}")
                sys.exit(1)
            convs = []
            for target in targets:
                with zf.open(target) as f:
                    data = json.load(f)
                chunk = data if isinstance(data, list) else data.get("conversations", [])
                convs.extend(chunk)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    # Only keep conversations that have actual messages after flattening
    return [c for c in convs if flatten_messages(c.get("mapping") or {})]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    print(f"Loading {input_path.name} ...")
    conversations = load_conversations(input_path)
    print(f"Found {len(conversations)} conversations with messages")

    conversations.sort(key=lambda c: c.get("create_time") or 0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing to {OUTPUT_DIR}\n")

    stems   = [note_stem(c) for c in conversations]
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

    index_path = OUTPUT_DIR / "00-ChatGPT-Index.md"
    index_path.write_text(format_index(conversations), encoding="utf-8")
    print(f"  Index updated: 00-ChatGPT-Index.md")

    print(f"\nDone.")
    print(f"  Written:  {written}")
    print(f"  Skipped:  {skipped}  (already exist)")
    print(f"  Index:    {index_path}")
    print(f"\nOpen 00-ChatGPT-Index.md in Obsidian to browse everything.")


if __name__ == "__main__":
    main()
