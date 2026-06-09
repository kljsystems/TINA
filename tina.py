"""
T.I.N.A — Totally Intelligent Neural Assistant
Main entry point — thin router, delegates everything to modules.

To add a new feature:
  - New tool:    add a file to tools/
  - New command: add a file to commands/
  - No changes needed here.
"""

import os
import sys
import time
import queue
import threading

# Ensure root dir is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load config first (sets up env vars)
import config

# Core modules
from core import voice_in, voice_out, brain, memory
from core import voice_manager as vm

# Tools & commands
import tools
import commands

# Dashboard
from dashboard import writer as dash

# Diagnostics
from diagnostics import run_diagnostics

# ── Shared state ──────────────────────────────────────────────────────────────

text_queue: queue.Queue[str] = queue.Queue()

def speak(text: str):
    """Speak text — updates dashboard state around TTS."""
    dash.set_state("speaking")
    dash.set_response(text)
    voice_out.speak(
        text,
        voice_id=vm.get_voice_id(),
        on_end=lambda: dash.set_state("listening"),
    )

def speak_raw(text: str):
    """Speak without changing active/timeout state — for commands."""
    speak(text)

# Context passed to command handlers
def build_ctx():
    return {
        "speak_raw":   speak_raw,
        "chat":        brain.chat,
        "voice_queue": voice_in.voice_queue,
        "text_queue":  text_queue,
        "brain":       brain,
        "dash":        dash,
    }

# ── Text input thread ─────────────────────────────────────────────────────────

def text_input_thread():
    while True:
        try:
            line = input("  You (text): ").strip()
            if line:
                text_queue.put(line)
        except (EOFError, KeyboardInterrupt):
            text_queue.put("goodbye tina")
            break

# ── Wake word helpers ─────────────────────────────────────────────────────────

def contains_wake_word(text: str) -> bool:
    return any(w in text for w in config.WAKE_WORDS)

def strip_wake_word(text: str) -> str:
    for w in config.WAKE_WORDS:
        text = text.replace(w, "").strip(" ,.")
    return text

def is_exit(text: str) -> bool:
    return any(cmd in text.lower() for cmd in config.EXIT_COMMANDS)

# ── Session summary ───────────────────────────────────────────────────────────

def save_session():
    if len(brain.conversation_history) > 2:
        print("  [Memory] Saving session summary...")
        summary = memory.generate_summary(brain.conversation_history)
        if summary:
            memory.save_summary(summary)

# ── Startup ───────────────────────────────────────────────────────────────────

def startup():
    # Run diagnostics
    diag = run_diagnostics()
    if diag.get("Anthropic API", {}).get("status") == "fail":
        print("  ⚠  Cannot start — Anthropic API failed.")
        sys.exit(1)

    # Init voice manager
    vm.init()

    print("\n" + "═" * 58)
    print("  T.I.N.A  —  Totally Intelligent Neural Assistant")
    print("═" * 58)
    print(f"  Voice  : {vm.get_voice_name()}")
    print(f"  Wake   : say 'Hey TINA'")
    print(f"  Text   : type anytime")
    print(f"  Timeout: {config.CONVERSATION_TIMEOUT}s silence → standby")
    print(f"  Exit   : say or type 'goodbye tina'")
    print("═" * 58 + "\n")

    # Register all tools with brain
    brain.register_tools(tools.ALL_DEFINITIONS, tools.handle)

    # Load memory
    mem_ctx = memory.build_context()
    brain.set_memory_context(mem_ctx)
    mem_data = memory.load()
    summaries = memory.load_summaries()
    if mem_ctx:
        print("  [Memory] Context loaded.\n")
    else:
        print("  [Memory] Starting fresh.\n")

    # Init dashboard
    dash.init_from_memory(mem_data, summaries)
    dash.set_voice(vm.get_voice_name())
    dash.start_heartbeat()

    # Load Whisper
    voice_in.load_whisper()

    # Start threads
    voice_in.start_listener(voice_out.is_speaking)
    threading.Thread(target=text_input_thread, daemon=True).start()

    # Greet
    time.sleep(0.5)
    greeting = brain.chat("Introduce yourself in one sentence as TINA. If you know the user's name from memory, greet them by name.")
    speak(greeting)

# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    startup()

    active          = False
    last_input_time = None
    ctx             = build_ctx()

    print("  Listening for wake word...\n")
    dash.set_state("standby")

    while True:

        # ── Timeout ────────────────────────────────────────────────────────
        if active and not voice_out.is_speaking.is_set():
            if time.time() - last_input_time > config.CONVERSATION_TIMEOUT:
                active = False
                save_session()
                dash.set_state("standby")
                speak("Standing by.")
                print("  Listening for wake word...\n")

        # ── Get input ──────────────────────────────────────────────────────
        user_input = None
        try:
            user_input = text_queue.get_nowait()
        except queue.Empty:
            pass

        if user_input is None:
            try:
                spoken = voice_in.voice_queue.get_nowait()
                if not active:
                    if contains_wake_word(spoken):
                        active = True
                        last_input_time = time.time()
                        cmd = strip_wake_word(spoken)
                        if cmd:
                            user_input = cmd
                        else:
                            speak("Hey! I'm here.")
                else:
                    user_input = spoken
            except queue.Empty:
                pass

        if user_input is None:
            time.sleep(0.05)
            continue

        # ── Exit ───────────────────────────────────────────────────────────
        if is_exit(user_input):
            save_session()
            farewell = brain.chat("Say a brief friendly TINA-style goodbye.")
            speak(farewell)
            print("\n  [TINA offline]\n")
            break

        # ── Dispatch to command modules ────────────────────────────────────
        print(f"  You: {user_input}")
        dash.set_heard(user_input)
        active = True
        last_input_time = time.time()

        handled, reply = commands.dispatch(user_input, ctx)

        if not handled:
            # Fall through to Claude
            dash.set_state("thinking")
            reply = brain.chat(user_input, on_tool_call=dash.set_tool)
            last_input_time = time.time()

        if reply:
            speak(reply)

        last_input_time = time.time()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\n  [TINA offline — Ctrl+C]\n")