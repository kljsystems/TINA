"""
TINA Core — Memory System
"""

import os
import json
from datetime import datetime
from config import MEMORY_FILE, SUMMARIES_DIR, ANTHROPIC_API_KEY, MODEL

os.makedirs(SUMMARIES_DIR, exist_ok=True)

DEFAULT_MEMORY = {"user": {"name": None, "location": None, "preferences": []}, "facts": [], "last_updated": None}

REMEMBER_TRIGGERS = ["remember that", "remember this", "make a note that", "make a note of",
                     "don't forget that", "note that", "keep in mind that", "save that"]
RECALL_TRIGGERS   = ["what do you remember", "what have you remembered", "show me your memory",
                     "what do you know about me", "what did we talk about"]
NAME_TRIGGERS     = ["my name is", "i am", "i'm", "call me"]
LOC_TRIGGERS      = ["i live in", "i'm in", "i am in", "i'm based in", "i'm from"]

def load() -> dict:
    if not os.path.exists(MEMORY_FILE):
        save(DEFAULT_MEMORY)
        return DEFAULT_MEMORY
    try:
        with open(MEMORY_FILE) as f:
            return json.load(f)
    except Exception:
        return DEFAULT_MEMORY

def save(mem: dict):
    mem["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2)

def update(key: str, value: str):
    mem = load()
    if key == "name":     mem["user"]["name"] = value
    elif key == "location": mem["user"]["location"] = value
    elif key == "preference":
        if value not in mem["user"]["preferences"]:
            mem["user"]["preferences"].append(value)
    elif key == "fact":
        mem["facts"].append({"fact": value, "added": datetime.now().isoformat()})
    save(mem)
    print(f"  [Memory] Saved: {key} = {value}")

def load_summaries(n: int = 5) -> list:
    try:
        files = sorted([f for f in os.listdir(SUMMARIES_DIR) if f.endswith(".json")])[-n:]
        result = []
        for fname in files:
            try:
                with open(os.path.join(SUMMARIES_DIR, fname)) as f:
                    result.append(json.load(f))
            except Exception:
                pass
        return result
    except Exception:
        return []

def save_summary(summary: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SUMMARIES_DIR, f"session_{ts}.json")
    with open(path, "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "summary": summary}, f, indent=2)
    print(f"  [Memory] Session summary saved.")

def build_context() -> str:
    parts = []
    mem = load()
    user = mem.get("user", {})
    lines = ["[TINA MEMORY]"]
    if user.get("name"):     lines.append(f"User's name: {user['name']}")
    if user.get("location"): lines.append(f"User's location: {user['location']}")
    if user.get("preferences"): lines.append(f"Preferences: {', '.join(user['preferences'])}")
    facts = mem.get("facts", [])
    if facts:
        lines.append("Remembered facts:")
        for f in facts[-20:]:
            lines.append(f"  - {f['fact']}")
    if len(lines) > 1:
        parts.append("\n".join(lines))
    summaries = load_summaries()
    if summaries:
        slines = ["[PAST SESSIONS]"]
        for s in summaries:
            try:
                dt = datetime.fromisoformat(s["timestamp"]).strftime("%A %d %B, %I:%M %p")
            except Exception:
                dt = s.get("timestamp", "")
            slines.append(f"\n{dt}:\n{s.get('summary','')}")
        parts.append("\n".join(slines))
    return "\n\n".join(parts)

def generate_summary(conversation_history: list) -> str:
    """Ask Claude to summarise the session."""
    try:
        import anthropic as ac
        client = ac.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=conversation_history + [{"role": "user", "content": (
                "Summarise this conversation in 3-5 concise bullet points covering: "
                "what was asked about, important facts mentioned, preferences expressed, "
                "and tasks completed. Plain bullet points starting with - only."
            )}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"  [Memory] Summary generation failed: {e}")
        return ""

def is_remember(text: str) -> bool:
    return any(t in text.lower() for t in REMEMBER_TRIGGERS)

def is_recall(text: str) -> bool:
    return any(t in text.lower() for t in RECALL_TRIGGERS)

def extract_fact(text: str) -> str:
    t = text.lower()
    for trigger in sorted(REMEMBER_TRIGGERS, key=len, reverse=True):
        if trigger in t:
            idx = t.index(trigger) + len(trigger)
            return text[idx:].strip(" .,")
    return text.strip()

def handle_remember(text: str) -> str:
    """Parse a remember command, update memory, return what was saved."""
    lower = text.lower()
    if any(t in lower for t in NAME_TRIGGERS):
        for t in NAME_TRIGGERS:
            if t in lower:
                name = lower.split(t)[-1].strip().split()[0].capitalize()
                update("name", name)
                return f"name:{name}"
    elif any(t in lower for t in LOC_TRIGGERS):
        for t in LOC_TRIGGERS:
            if t in lower:
                loc = text.split(t)[-1].strip(" .")
                update("location", loc)
                return f"location:{loc}"
    else:
        fact = extract_fact(text)
        update("fact", fact)
        return f"fact:{fact}"
    return ""


def get_recall_response(mem: dict, summaries: list) -> str:
    """Format memory for recall presentation."""
    parts = []
    core = build_context()
    if core:
        parts.append(core)
    if not parts:
        return "I don't have any stored memories yet."
    return "\n\n".join(parts)