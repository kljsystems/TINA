"""Continuous wake-word detection using faster-whisper tiny model.

Runs in a daemon thread, records 2-second audio chunks, transcribes locally,
and fires a callback when 'tina' appears in the transcript.
"""
import threading
import asyncio
import time

_active  = False
_paused  = False
_thread  = None
_model   = None


def _load_model():
    global _model
    if _model is None:
        print("[wake-word] loading faster-whisper tiny.en model (first run may download ~40 MB)…")
        from faster_whisper import WhisperModel
        _model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        print("[wake-word] model ready")
    return _model


def _detect_loop(loop, callback):
    global _active, _paused

    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as e:
        print(f"[wake-word] missing dependency — {e}")
        print("[wake-word] install with:  pip install faster-whisper sounddevice")
        return

    try:
        model = _load_model()
    except Exception as e:
        print(f"[wake-word] model load failed: {e}")
        return

    WHISPER_RATE = 16000   # faster-whisper expects 16 kHz
    COOLDOWN     = 5.0     # seconds before re-triggering
    last_trig    = 0.0

    # Record at the device's native rate to avoid forcing WASAPI to resample
    # the entire Windows audio pipeline (which makes all system audio robotic).
    try:
        dev_info    = sd.query_devices(kind="input")
        NATIVE_RATE = int(dev_info["default_samplerate"])
    except Exception:
        NATIVE_RATE = 48000
    CHUNK = NATIVE_RATE * 2  # 2-second windows at native rate

    def _resample(flat):
        """Downsample from NATIVE_RATE to WHISPER_RATE using numpy interpolation."""
        if NATIVE_RATE == WHISPER_RATE:
            return flat
        target_len = int(len(flat) * WHISPER_RATE / NATIVE_RATE)
        # Integer ratio → fast decimation; otherwise linear interpolation
        if NATIVE_RATE % WHISPER_RATE == 0:
            return flat[:: NATIVE_RATE // WHISPER_RATE]
        return np.interp(
            np.linspace(0, len(flat) - 1, target_len),
            np.arange(len(flat)),
            flat,
        ).astype(np.float32)

    print(f"[wake-word] recording at {NATIVE_RATE} Hz (device native), downsampling to {WHISPER_RATE} Hz for transcription")
    print("[wake-word] listening for 'tina'…")
    asyncio.run_coroutine_threadsafe(callback("ready", ""), loop)

    while _active:
        if _paused:
            time.sleep(0.3)
            continue
        try:
            audio = sd.rec(CHUNK, samplerate=NATIVE_RATE, channels=1, dtype="float32")
            sd.wait()
            if not _active:
                break

            flat = _resample(audio.flatten())

            # Skip silent chunks — saves transcription overhead
            if float(np.abs(flat).mean()) < 0.003:
                continue

            segments, _ = model.transcribe(
                flat, language="en", beam_size=1, vad_filter=True, vad_parameters={"min_silence_duration_ms": 300}
            )
            text = " ".join(s.text for s in segments).lower().strip()
            if not text:
                continue

            if "tina" in text:
                now = time.time()
                if now - last_trig > COOLDOWN and not _paused:
                    last_trig = now
                    print(f"[wake-word] triggered — heard: '{text}'")
                    asyncio.run_coroutine_threadsafe(callback("triggered", text), loop)

        except Exception as e:
            print(f"[wake-word] loop error: {e}")
            time.sleep(1)


def start(loop, callback):
    """Start the wake-word detector in a daemon thread."""
    global _active, _thread
    if _active:
        return
    _active = True
    _thread = threading.Thread(
        target=_detect_loop,
        args=(loop, callback),
        daemon=True,
        name="tina-wake-word",
    )
    _thread.start()


def stop():
    global _active
    _active = False
    print("[wake-word] stopped")


def pause():
    """Temporarily suspend detection (e.g. while TTS is playing)."""
    global _paused
    _paused = True


def resume():
    """Resume detection after a pause."""
    global _paused
    _paused = False
