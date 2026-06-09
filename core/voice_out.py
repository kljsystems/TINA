"""
TINA Core — Voice Output (TTS)
ElevenLabs with pyttsx3 fallback.
"""

import os
import time
import threading
import tempfile
from config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL, ELEVENLABS_FORMAT

tts_lock       = threading.Lock()
is_speaking    = threading.Event()

def elevenlabs_speak(text: str, voice_id: str) -> bool:
    if not ELEVENLABS_API_KEY or not voice_id:
        return False
    try:
        import pygame
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio_gen = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=ELEVENLABS_MODEL,
            output_format=ELEVENLABS_FORMAT,
        )
        audio_bytes = b"".join(chunk for chunk in audio_gen if chunk)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=2048)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.set_volume(1.0)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
        pygame.mixer.quit()
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"  [ElevenLabs] Error: {e} — falling back to pyttsx3")
        return False

def pyttsx3_speak(text: str):
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        for v in voices:
            if "david" in v.name.lower() or "male" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
        engine.setProperty("rate", 185)
        engine.setProperty("volume", 0.95)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"  [pyttsx3] Error: {e}")

def speak(text: str, voice_id: str = "", on_start=None, on_end=None):
    """Speak text aloud. Calls on_start/on_end callbacks for dashboard updates."""
    print(f"\n  TINA: {text}\n")
    is_speaking.set()
    if on_start:
        try: on_start()
        except: pass
    with tts_lock:
        success = elevenlabs_speak(text, voice_id)
        if not success:
            pyttsx3_speak(text)
    is_speaking.clear()
    if on_end:
        try: on_end()
        except: pass