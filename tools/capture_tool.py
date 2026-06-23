"""TINA Tool — Capture Inbox (drop items into 00-Inbox/ for the pipeline to process)"""
import os
from pathlib import Path
from datetime import datetime

try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import VAULT_DIR
    VAULT_ROOT = Path(VAULT_DIR)
except Exception:
    VAULT_ROOT = Path(r"C:\Users\nrlocal\Desktop\KLJ\Memory")

INBOX_DIR = VAULT_ROOT / "00-Inbox"

DEFINITIONS = [
    {
        "name": "capture_item",
        "description": (
            "Drop a note, URL, idea, or task into the inbox pipeline for automatic classification and routing. "
            "Use this when Ky says 'capture this', 'remember this', 'note this down', 'add this to my inbox', "
            "or any variant of wanting to save something for later without acting on it now. "
            "The pipeline classifies the item (project / action / idea / reference) every 15 minutes "
            "and routes it to the right vault folder automatically. Projects trigger Charlie to auto-research."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type":        "string",
                    "description": "The raw text, URL, idea, or note to capture — exactly as Ky said or shared it.",
                },
                "source": {
                    "type":        "string",
                    "enum":        ["voice", "text", "url", "paste"],
                    "description": "How this item was submitted. Default: text.",
                },
            },
            "required": ["content"],
        },
    }
]


def _capture(content: str, source: str = "text") -> str:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    now       = datetime.now()
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    filename  = f"{timestamp}-capture.md"
    filepath  = INBOX_DIR / filename

    note = (
        f"---\n"
        f"date: {now.isoformat(timespec='seconds')}\n"
        f"source: {source}\n"
        f"status: unprocessed\n"
        f"---\n\n"
        f"{content}"
    )
    filepath.write_text(note, encoding="utf-8")
    return (
        f"Captured: {filename}\n"
        "The pipeline will classify and route this within 15 minutes. "
        "If it's a project, Charlie will start researching automatically."
    )


def handle(name: str, inputs: dict) -> str:
    if name == "capture_item":
        return _capture(inputs.get("content", ""), inputs.get("source", "text"))
    return f"Unknown tool: {name}"
