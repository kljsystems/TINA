"""
TINA Command — Voice Switching
"""

import time
import queue

TRIGGERS = ["change your voice", "switch voice", "change voice", "switch your voice", "tina change voice", "voice list", "voice set"]

def handle(text: str, ctx: dict) -> str:
    from core import voice_manager as vm
    speak   = ctx.get("speak_raw")
    vq      = ctx.get("voice_queue")
    tq      = ctx.get("text_queue")
    t = text.lower().strip()

    if t.startswith("voice list"):
        print(vm.format_voice_list())
        return f"I have {len(vm.voices)} voices available. Use 'voice set' followed by the name or number to switch."

    if t.startswith("voice set"):
        parts = t.split(None, 2)
        target = parts[2] if len(parts) > 2 else ""
        result = vm.select_voice(target)
        if result == "cancel":
            return "Keeping the current voice."
        if result:
            return f"Switching to {result}. How does this sound?"
        return f"I couldn't find a voice matching that."

    # Interactive voice change
    print(vm.format_voice_list())
    if speak:
        speak(f"I have {len(vm.voices)} voices. Say the number or name.")

    deadline = time.time() + 20
    while time.time() < deadline:
        for q in [tq, vq]:
            if q is None: continue
            try:
                raw = q.get_nowait()
                result = vm.select_voice(raw)
                if result == "cancel":
                    return "Keeping the current voice."
                if result:
                    return f"Switching to {result}. How does this sound?"
            except queue.Empty:
                pass
        time.sleep(0.05)

    return "Voice selection timed out. Keeping the current voice."