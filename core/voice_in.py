"""
TINA Core — Voice Input (STT)
Faster-Whisper with VAD-based end-of-speech detection.
"""

import time
import threading
import queue
import numpy as np
import sounddevice as sd
from config import (
    WHISPER_MODEL_SIZE, SAMPLE_RATE, SILENCE_FRAMES,
    SPEECH_FRAMES, MAX_RECORD_SEC, SILENCE_RMS, FRAME_MS
)

voice_queue: queue.Queue[str] = queue.Queue()
whisper_model = None

HALLUCINATIONS = {
    "thank you", "thanks for watching", "you", ".", "",
    "thank you for watching", "bye", "the", "i", "a", "um", "uh", "hmm",
}

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

def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio ** 2)))

def is_silent(audio: np.ndarray) -> bool:
    return rms(audio) < 0.008

def transcribe(audio: np.ndarray) -> str:
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

def start_listener(is_speaking_event: threading.Event):
    """Start the always-on VAD voice listener thread."""
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

    def _listen():
        while whisper_model is None:
            time.sleep(0.1)
        print("  [Whisper] Listener active.\n")
        while True:
            if is_speaking_event.is_set():
                time.sleep(0.1)
                continue
            try:
                frames, speech_count, silence_count, recording = [], 0, 0, False
                while True:
                    if is_speaking_event.is_set():
                        frames = []
                        break
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
                    continue
                audio_data = np.concatenate(frames)
                if is_silent(audio_data):
                    continue
                text = transcribe(audio_data)
                if text and text not in HALLUCINATIONS and len(text) > 2:
                    print(f"  [Heard]: {text}")
                    voice_queue.put(text)
            except Exception as e:
                print(f"  [Voice] Error: {e}")
                time.sleep(0.5)

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    return t