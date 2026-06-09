"""
TINA Startup Diagnostics
Tests all components and returns a status report.
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
TAVILY_API_KEY      = os.getenv("TAVILY_API_KEY", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID       = os.getenv("GOOGLE_CSE_ID", "")

PASS  = "✓"
FAIL  = "✗"
WARN  = "⚠"

results = {}

def check(name, fn):
    try:
        status, msg = fn()
        results[name] = {"status": status, "msg": msg}
        symbol = PASS if status == "ok" else WARN if status == "warn" else FAIL
        color  = "\033[92m" if status == "ok" else "\033[93m" if status == "warn" else "\033[91m"
        reset  = "\033[0m"
        print(f"  {color}{symbol}{reset}  {name:<28} {msg}")
    except Exception as e:
        results[name] = {"status": "fail", "msg": str(e)}
        print(f"  \033[91m{FAIL}\033[0m  {name:<28} {e}")

def test_anthropic():
    if not ANTHROPIC_API_KEY:
        return "fail", "ANTHROPIC_API_KEY missing from .env"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        r = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role":"user","content":"say ok"}]
        )
        return "ok", "claude sonnet 4.6 — connected"
    except Exception as e:
        return "fail", f"API error: {str(e)[:60]}"

def test_elevenlabs():
    if not ELEVENLABS_API_KEY:
        return "fail", "ELEVENLABS_API_KEY missing from .env"
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        voices = client.voices.get_all()
        count = len(voices.voices)
        return "ok", f"connected — {count} voices available"
    except Exception as e:
        err = str(e)
        if "401" in err or "missing_permissions" in err:
            return "fail", "API key invalid or missing permissions"
        if "402" in err or "payment" in err:
            return "warn", "free tier — library voices restricted"
        return "fail", f"error: {err[:60]}"

def test_elevenlabs_tts():
    if not ELEVENLABS_API_KEY:
        return "fail", "no API key"
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            voice_id="onwK4e9ZLuTAKqWW03F9",
            text="test",
            model_id="eleven_turbo_v2_5",
            output_format="mp3_44100_128",
        )
        data = b"".join(chunk for chunk in audio if chunk)
        if len(data) > 100:
            return "ok", f"TTS working — {len(data)} bytes generated"
        return "fail", "TTS returned empty audio"
    except Exception as e:
        err = str(e)
        if "402" in err or "payment" in err:
            return "fail", "TTS blocked — free tier cannot use this voice via API"
        if "401" in err:
            return "fail", "TTS blocked — API key missing TTS permission"
        return "fail", f"TTS error: {err[:60]}"

def test_whisper():
    try:
        from faster_whisper import WhisperModel
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return "ok", f"faster-whisper ready — {device.upper()}"
    except ImportError:
        try:
            from faster_whisper import WhisperModel
            return "ok", "faster-whisper ready — CPU"
        except Exception as e:
            return "fail", f"faster-whisper not installed: {e}"

def test_microphone():
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        inputs = [d for d in devices if d['max_input_channels'] > 0]
        if not inputs:
            return "fail", "no input devices found"
        default = sd.query_devices(kind='input')
        return "ok", f"microphone: {default['name'][:40]}"
    except Exception as e:
        return "fail", f"sounddevice error: {e}"

def test_speakers():
    try:
        import sounddevice as sd
        default = sd.query_devices(kind='output')
        return "ok", f"output: {default['name'][:40]}"
    except Exception as e:
        return "fail", f"output device error: {e}"

def test_pygame():
    try:
        import pygame
        pygame.mixer.pre_init(44100,-16,1,2048)
        pygame.mixer.init()
        pygame.mixer.quit()
        return "ok", f"pygame {pygame.version.ver} — audio ready"
    except Exception as e:
        return "fail", f"pygame error: {e}"

def test_tavily():
    if not TAVILY_API_KEY:
        return "fail", "TAVILY_API_KEY missing from .env"
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        r = client.search("test", max_results=1)
        return "ok", "tavily search — connected"
    except Exception as e:
        return "fail", f"tavily error: {e}"

def test_weather():
    if not OPENWEATHER_API_KEY:
        return "warn", "OPENWEATHER_API_KEY missing — weather unavailable"
    try:
        import requests
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q":"Sydney,AU","appid":OPENWEATHER_API_KEY,"units":"metric"},
            timeout=5
        )
        if r.status_code == 200:
            return "ok", "openweathermap — connected"
        if r.status_code == 401:
            return "warn", "API key not yet activated (up to 2 hours after signup)"
        return "warn", f"status {r.status_code}"
    except Exception as e:
        return "warn", f"weather error: {e}"

def test_google_calendar():
    creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
    token_file  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "token.json")
    if not os.path.exists(creds_file):
        return "warn", "credentials.json not found — calendar unavailable"
    if not os.path.exists(token_file):
        return "warn", "not yet authorised — run TINA and type 'what's on my calendar'"
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(token_file)
        if creds and creds.valid:
            return "ok", "google calendar — authorised"
        return "warn", "token expired — will refresh on next use"
    except Exception as e:
        return "warn", f"calendar check error: {e}"

def test_memory():
    memory_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "memory.json")
    summaries   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "summaries")
    if not os.path.exists(memory_file):
        return "warn", "no memory.json yet — will create on first use"
    try:
        import json
        with open(memory_file) as f:
            mem = json.load(f)
        facts = len(mem.get("facts",[]))
        sessions = len(os.listdir(summaries)) if os.path.exists(summaries) else 0
        user = mem.get("user",{}).get("name","unknown")
        return "ok", f"memory loaded — user: {user}, {facts} facts, {sessions} sessions"
    except Exception as e:
        return "fail", f"memory error: {e}"

def test_pyttsx3():
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        engine.stop()
        return "ok", f"pyttsx3 fallback ready — {len(voices)} voices"
    except Exception as e:
        return "fail", f"pyttsx3 error: {e}"

def run_diagnostics() -> dict:
    print("\n" + "═"*55)
    print("  T.I.N.A — Startup Diagnostics")
    print("═"*55)

    print("\n  [ AI & Voice ]")
    check("Anthropic API",       test_anthropic)
    check("ElevenLabs auth",     test_elevenlabs)
    check("ElevenLabs TTS",      test_elevenlabs_tts)
    check("pyttsx3 fallback",    test_pyttsx3)

    print("\n  [ Audio Hardware ]")
    check("Microphone",          test_microphone)
    check("Speakers / output",   test_speakers)
    check("Pygame audio",        test_pygame)

    print("\n  [ Speech Recognition ]")
    check("Faster-Whisper",      test_whisper)

    print("\n  [ Tools & APIs ]")
    check("Tavily search",       test_tavily)
    check("OpenWeatherMap",      test_weather)
    check("Google Calendar",     test_google_calendar)

    print("\n  [ Memory ]")
    check("Memory system",       test_memory)

    total  = len(results)
    passed = sum(1 for r in results.values() if r["status"]=="ok")
    warned = sum(1 for r in results.values() if r["status"]=="warn")
    failed = sum(1 for r in results.values() if r["status"]=="fail")

    print("\n" + "─"*55)
    print(f"  \033[92m{passed} passed\033[0m  ·  \033[93m{warned} warnings\033[0m  ·  \033[91m{failed} failed\033[0m")

    if failed > 0:
        print("\n  Failed components:")
        for name, r in results.items():
            if r["status"] == "fail":
                print(f"    ✗ {name}: {r['msg']}")

    print("═"*55 + "\n")
    return results

if __name__ == "__main__":
    run_diagnostics()