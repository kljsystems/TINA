"""
TINA Dashboard Writer
Writes tina_status.json so dashboard.html can read live status.
"""

import os
import json
import time
import threading
from datetime import datetime
from config import STATUS_FILE

os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)

_lock   = threading.Lock()
_status = {
    "state": "standby", "last_heard": "", "last_response": "",
    "last_tool": "", "last_tool_time": "", "user_name": "",
    "user_location": "", "facts_count": 0, "sessions_count": 0,
    "voice_name": "", "tools_count": 5, "updated": "",
}

def _write():
    _status["updated"] = datetime.now().isoformat()
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(_status, f, indent=2)
    except Exception as e:
        print(f"  [Dashboard] Write error: {e}")

def set_state(state: str):
    with _lock: _status["state"] = state; _write()

def set_heard(text: str):
    with _lock: _status["last_heard"] = text; _write()

def set_response(text: str):
    with _lock: _status["last_response"] = text[:120] + ("..." if len(text)>120 else ""); _write()

def set_tool(name: str):
    with _lock:
        _status["last_tool"] = name
        _status["last_tool_time"] = datetime.now().strftime("%I:%M %p")
        _write()

def set_voice(name: str):
    with _lock: _status["voice_name"] = name; _write()

def init_from_memory(memory: dict, summaries: list):
    user = memory.get("user", {})
    with _lock:
        if user.get("name"):     _status["user_name"]     = user["name"]
        if user.get("location"): _status["user_location"] = user["location"]
        _status["facts_count"]    = len(memory.get("facts", []))
        _status["sessions_count"] = len(summaries)
        _write()

def start_heartbeat():
    def _beat():
        while True:
            with _lock: _write()
            time.sleep(3)
    threading.Thread(target=_beat, daemon=True).start()