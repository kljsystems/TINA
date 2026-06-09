import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
TINA Command — System Diagnostics
Triggered by: "run a system check", "run diagnostics", "system status", "how are you doing"
"""

TRIGGERS = [
    "run a system check", "run diagnostics", "system check",
    "system status", "check your systems", "self diagnostic",
    "are you working properly", "everything working",
]

def handle(text: str, ctx: dict) -> str:
    from diagnostics import run_diagnostics
    speak = ctx.get("speak_raw")   # speak without waiting for reply

    if speak:
        speak("Running a full system diagnostic now. Give me a moment.")

    results = run_diagnostics()

    passed = sum(1 for r in results.values() if r["status"] == "ok")
    warned = sum(1 for r in results.values() if r["status"] == "warn")
    failed = sum(1 for r in results.values() if r["status"] == "fail")
    total  = len(results)

    parts = []

    if failed == 0 and warned == 0:
        parts.append(f"All {total} systems are fully operational.")
    elif failed == 0:
        parts.append(f"{passed} systems online, {warned} with minor warnings.")
    else:
        parts.append(f"{passed} systems online, {failed} failed, {warned} with warnings.")

    # Mention specific failures
    failures = [name for name, r in results.items() if r["status"] == "fail"]
    warnings = [name for name, r in results.items() if r["status"] == "warn"]

    if failures:
        parts.append(f"Failed: {', '.join(failures)}.")
    if warnings:
        parts.append(f"Warnings on: {', '.join(warnings)}.")

    # Specific helpful notes
    if results.get("ElevenLabs TTS", {}).get("status") == "fail":
        parts.append("Voice output is falling back to the built-in synthesiser.")
    if results.get("OpenWeatherMap", {}).get("status") == "warn":
        parts.append("Weather may be using search as a fallback.")
    if results.get("Google Calendar", {}).get("status") == "warn":
        parts.append("Calendar token will refresh on next use.")

    return " ".join(parts)