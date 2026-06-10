import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
TINA Core — Voice Input (STT)
Supports two engines:
  - deepgram: cloud-based, fast, accurate, great for Australian accents
  - whisper:  offline, no API needed, best with GPU

Set STT_ENGINE in config.py to switch.
"""

import time
import threading
import queue
import numpy as np
import sounddevice as sd
from config import (
    WHISPER_MODEL_SIZE, SAMPLE_RATE, SILENCE_FRAMES,
    SPEECH_FRAMES, MAX_RECORD_SEC, SILENCE_RMS, FRAME_MS,
    STT_ENGINE, DEEPGRAM_API_KEY
)

voice_queue: queue.Queue[str] = queue.Queue()
whisper_model = None

HALLUCINATIONS = {
    "thank you", "thanks for watching", "you", ".", "",
    "thank you for watching", "bye", "the", "i", "a", "um", "uh", "hmm",
}

# ── Shared audio helpers ──────────────────────────────────────────────────────

def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio ** 2)))

def is_silent(audio: np.ndarray) -> bool:
    return rms(audio) < 0.008

# ── Whisper ───────────────────────────────────────────────────────────────────

def load_whisper():
    global whisper_model
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    print(f"  [Whisper] Loading '{WHISPER_MODEL_SIZE}' model on {device.upper()}...")
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=compute)
    print(f"  [Whisper] Ready.\n")
    return whisper_model

def transcribe_whisper(audio: np.ndarray) -> str:
    if whisper_model is None:
        return ""
    segments, _ = whisper_model.transcribe(
        audio,
        language="en",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200, "threshold": 0.35},
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
    )
    return " ".join(s.text for s in segments).strip().lower()

# ── Deepgram ──────────────────────────────────────────────────────────────────

def transcribe_deepgram(audio: np.ndarray) -> str:
    """Send audio to Deepgram and return transcription."""
    if not DEEPGRAM_API_KEY:
        return ""
    try:
        import httpx
        # Convert float32 to int16 for Deepgram
        audio_int16 = (audio * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "audio/raw",
            },
            params={
                "encoding": "linear16",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "language": "en-AU",       # Australian English
                "model": "nova-2",         # best accuracy model
                "punctuate": "false",
                "smart_format": "false",
            },
            content=audio_bytes,
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
            return transcript.strip().lower()
        else:
            print(f"  [Deepgram] Error {response.status_code}: {response.text[:100]}")
            return ""
    except Exception as e:
        print(f"  [Deepgram] Error: {e}")
        return ""

# ── VAD-based recorder ────────────────────────────────────────────────────────

def record_utterance(is_speaking_event: threading.Event) -> np.ndarray | None:
    """
    Record a single utterance using VAD.
    Returns audio array or None if nothing was recorded.
    """
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)
    frames, speech_count, silence_count, recording = [], 0, 0, False

    while True:
        if is_speaking_event.is_set():
            return None

        frame = sd.rec(FRAME_SAMPLES, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        fd = frame.flatten()
        loud = rms(fd) >= SILENCE_RMS

        if not recording:
            if loud:
                speech_count += 1
                frames.append(fd)
                if speech_count >= SPEECH_FRAMES:
                    recording = True
                    silence_count = 0
            else:
                speech_count = max(0, speech_count - 1)
                frames = frames[-SPEECH_FRAMES:]
        else:
            frames.append(fd)
            if not loud:
                silence_count += 1
                if silence_count >= SILENCE_FRAMES:
                    break
            else:
                silence_count = 0
            if len(frames) * FRAME_MS / 1000 >= MAX_RECORD_SEC:
                break

    if not frames or not recording:
        return None

    audio = np.concatenate(frames)
    return None if is_silent(audio) else audio

# ── Main listener thread ──────────────────────────────────────────────────────

def start_listener(is_speaking_event: threading.Event):
    """Start the always-on VAD voice listener thread."""

    engine = STT_ENGINE.lower()

    # Load Whisper if needed
    if engine == "whisper" or engine == "both":
        load_whisper()

    if engine == "deepgram" and not DEEPGRAM_API_KEY:
        print("  [STT] Deepgram key missing — falling back to Whisper")
        load_whisper()

    print(f"  [STT] Engine: {engine.upper()}\n")

    def _listen():
        while True:
            if is_speaking_event.is_set():
                time.sleep(0.1)
                continue
            try:
                audio = record_utterance(is_speaking_event)
                if audio is None:
                    continue

                # Choose transcription engine
                text = ""
                if engine == "deepgram" and DEEPGRAM_API_KEY:
                    text = transcribe_deepgram(audio)
                    if not text:  # fallback to whisper if deepgram fails
                        print("  [STT] Deepgram failed — trying Whisper fallback")
                        if whisper_model:
                            text = transcribe_whisper(audio)
                elif engine == "whisper" or whisper_model:
                    text = transcribe_whisper(audio)

                if text and text not in HALLUCINATIONS and len(text) > 2:
                    print(f"  [Heard]: {text}")
                    voice_queue.put(text)

            except Exception as e:
                print(f"  [Voice] Error: {e}")
                time.sleep(0.5)

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    return t