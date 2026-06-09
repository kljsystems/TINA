import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
TINA Core — Voice Manager
Manages ElevenLabs voice selection and persistence.
"""

import os
import json
from config import VOICES_FILE, PREFS_FILE, DEFAULT_VOICES

os.makedirs(os.path.dirname(VOICES_FILE), exist_ok=True)

current_voice: dict = {}
voices: list = []

def load_voices() -> list:
    if not os.path.exists(VOICES_FILE):
        _save_voices(DEFAULT_VOICES)
        return list(DEFAULT_VOICES)
    try:
        with open(VOICES_FILE) as f:
            return json.load(f)
    except Exception:
        return list(DEFAULT_VOICES)

def _save_voices(v: list):
    os.makedirs(os.path.dirname(VOICES_FILE), exist_ok=True)
    with open(VOICES_FILE, "w") as f:
        json.dump(v, f, indent=2)

def load_prefs() -> dict:
    if not os.path.exists(PREFS_FILE):
        return {}
    try:
        with open(PREFS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_prefs(prefs: dict):
    os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

def get_default_voice() -> dict:
    prefs = load_prefs()
    vid = prefs.get("default_voice_id")
    if vid:
        match = next((v for v in voices if v["id"] == vid), None)
        if match:
            return match
    return voices[0] if voices else DEFAULT_VOICES[0]

def set_voice(v: dict, persist: bool = False):
    global current_voice
    current_voice = v
    print(f"  [Voice] Switched to: {v['name']} — {v['description']}")
    if persist:
        prefs = load_prefs()
        prefs["default_voice_id"] = v["id"]
        save_prefs(prefs)
        print(f"  [Voice] Saved as default.")

def get_voice_id() -> str:
    return current_voice.get("id", "")

def get_voice_name() -> str:
    return current_voice.get("name", "")

def format_voice_list() -> str:
    lines = ["  Available voices:"]
    for i, v in enumerate(voices, 1):
        marker = " ◀" if v["id"] == current_voice.get("id") else ""
        lines.append(f"    {i}. {v['name']} — {v['description']}{marker}")
    lines.append("\n  Say the number or name to switch. Say 'cancel' to keep current.")
    return "\n".join(lines)

def word_to_number(text: str):
    clean = text.strip()
    if clean.isdigit():
        return int(clean)
    word_map = {
        "one":1,"two":2,"three":3,"four":4,"five":5,
        "six":6,"seven":7,"eight":8,"nine":9,"ten":10,
        "first":1,"second":2,"third":3,"fourth":4,"fifth":5,
    }
    for word in clean.lower().split():
        word = word.strip(".,!?")
        if word in word_map:
            return word_map[word]
        if word.isdigit():
            return int(word)
    return None

def select_voice(raw: str) -> bool:
    """Try to interpret raw input as a voice selection. Returns True if handled."""
    raw = raw.strip().lower()
    cancels = ("cancel","nevermind","never mind","keep current","keep it","no thanks","forget it","stop")
    if any(c in raw for c in cancels):
        return "cancel"
    num = word_to_number(raw)
    if num is not None:
        idx = num - 1
        if 0 <= idx < len(voices):
            set_voice(voices[idx], persist=True)
            return voices[idx]["name"]
        return None
    filler = {"please","hey","use","switch","to","voice","number","pick","choose","select","the","i","want","would","like","tina"}
    words = [w.strip(".,!?") for w in raw.split() if w.strip(".,!?") not in filler]
    matches = [v for v in voices if any(w in v["name"].lower() for w in words)]
    if len(matches) == 1:
        set_voice(matches[0], persist=True)
        return matches[0]["name"]
    return None

def init():
    global voices
    voices = load_voices()
    set_voice(get_default_voice())
    