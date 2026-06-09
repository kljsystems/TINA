import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
TINA Commands — Auto-registration
Drop a new file in this folder and it's automatically available.
Each command module must expose: TRIGGERS list and handle(text, ctx) function.
"""

import importlib
import os

_commands = []

def _load():
    cmd_dir = os.path.dirname(__file__)
    for fname in os.listdir(cmd_dir):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        mod_name = f"commands.{fname[:-3]}"
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "TRIGGERS") and hasattr(mod, "handle"):
                _commands.append(mod)
        except Exception as e:
            print(f"  [Commands] Failed to load {fname}: {e}")

_load()

def dispatch(text: str, ctx: dict):
    """
    Try each command module. Returns (handled: bool, reply: str).
    ctx contains shared state: speak, chat, voices, etc.
    """
    t = text.lower()
    for cmd in _commands:
        if any(trigger in t for trigger in cmd.TRIGGERS):
            try:
                reply = cmd.handle(text, ctx)
                return True, reply
            except Exception as e:
                print(f"  [Commands] Error in {cmd.__name__}: {e}")
                return True, "I ran into an issue with that command."
    return False, ""

def reload():
    """Hot-reload all command modules without restarting TINA."""
    global _commands
    _commands = []
    _load()
    print(f"  [Commands] Reloaded — {len(_commands)} commands active.")