"""TINA Tool — Video processing: download from URL + extract frames + transcribe audio.

Requires:
  - yt-dlp  (pip install yt-dlp)   — video downloading
  - ffmpeg  (system install)        — frame extraction and audio stripping
  - httpx   (already in env)        — Deepgram transcription REST call
"""
import os
import sys
import base64
import subprocess
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import DEEPGRAM_API_KEY, GENERATED_DOCS_DIR
except Exception:
    DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY", "")
    GENERATED_DOCS_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "KLJ", "Generated Docs")

VIDEO_DIR = os.path.join(GENERATED_DOCS_DIR, "Videos")


DEFINITIONS = [
    {
        "name": "video_download",
        "description": (
            "Download a video from TikTok, Instagram, YouTube, X/Twitter, or any public URL. "
            "Returns the local file path of the saved video. "
            "After downloading, call video_process to extract frames and transcribe the audio."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type":        "string",
                    "description": "Full URL of the video to download.",
                },
                "output_name": {
                    "type":        "string",
                    "description": "Optional filename without extension. Defaults to the video title.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "youtube_transcript",
        "description": (
            "Get the full text transcript of a YouTube video without downloading it. "
            "Much faster than video_download + video_process — use this whenever you only need "
            "what was said, not the visuals. Works on most YouTube videos with captions "
            "(auto-generated or manually added). Falls back to an error if the video has no captions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full YouTube video URL (youtube.com/watch?v=... or youtu.be/...).",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "video_process",
        "description": (
            "Analyse a local video file. Extracts evenly-spaced frames as images and transcribes "
            "the audio using Deepgram. Returns the transcript plus all frames so you can see and "
            "hear what's in the video. Call after video_download, or point at any saved video file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Absolute path to the local video file.",
                },
                "frames": {
                    "type":        "integer",
                    "description": "Number of frames to extract (default 10, max 20). More frames = better visual coverage.",
                },
            },
            "required": ["path"],
        },
    },
]


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _download(url: str, output_name: str | None) -> str:
    os.makedirs(VIDEO_DIR, exist_ok=True)
    template = os.path.join(VIDEO_DIR, f"{output_name}.%(ext)s" if output_name else "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--format",              "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--output",              template,
        "--no-playlist",
        "--print",               "after_move:filepath",
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            err = (result.stderr or "unknown error")[-400:]
            return f"Download failed: {err}"

        # yt-dlp --print after_move:filepath prints the final path on stdout
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        path = lines[-1] if lines else ""
        if path and os.path.exists(path):
            return f"Downloaded to: {path}"

        # Fallback: newest file in VIDEO_DIR
        files = sorted(
            [os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR)],
            key=os.path.getmtime, reverse=True
        )
        return f"Downloaded to: {files[0]}" if files else f"Download completed. Check {VIDEO_DIR}"

    except FileNotFoundError:
        return (
            "yt-dlp not found. Ask Sam to install it:\n"
            "  pip install yt-dlp\n"
            "Then try again."
        )
    except subprocess.TimeoutExpired:
        return "Download timed out after 3 minutes. Video may be too large."
    except Exception as e:
        return f"Download error: {e}"


def _transcribe(audio_path: str) -> str:
    """Send an audio file to Deepgram REST API and return the transcript."""
    if not DEEPGRAM_API_KEY:
        return ""
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 500:
        return ""
    try:
        import httpx
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://api.deepgram.com/v1/listen",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type":  "audio/mp3",
                },
                content=audio_bytes,
                params={"punctuate": "true", "smart_format": "true", "model": "nova-2"},
            )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        return data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except Exception:
        return ""


def _process(path: str, frames: int) -> dict | str:
    if not os.path.exists(path):
        return f"File not found: {path}"
    if not _ffmpeg_available():
        return (
            "ffmpeg not found on PATH. Install it from https://ffmpeg.org/download.html "
            "and make sure it's on your system PATH, then try again."
        )

    frames = min(max(1, frames or 10), 20)

    # Get video metadata
    duration = 0.0
    title    = os.path.basename(path)
    try:
        probe  = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        info     = json.loads(probe.stdout)
        duration = float(info.get("format", {}).get("duration", 0))
        tags     = info.get("format", {}).get("tags", {})
        title    = tags.get("title") or tags.get("TITLE") or title
    except Exception:
        pass

    frame_list = []
    transcript = ""

    with tempfile.TemporaryDirectory() as tmp:
        # Evenly-spaced timestamps across the video
        if duration > 0:
            interval   = duration / (frames + 1)
            timestamps = [round(interval * i, 2) for i in range(1, frames + 1)]
        else:
            timestamps = [i * 3.0 for i in range(frames)]

        extracted_ts = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(tmp, f"frame_{i:03d}.jpg")
            r = subprocess.run(
                ["ffmpeg", "-ss", str(ts), "-i", path,
                 "-vframes", "1", "-vf", "scale=720:-1", "-q:v", "5", "-y", frame_path],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0 and os.path.exists(frame_path):
                with open(frame_path, "rb") as f:
                    frame_list.append({
                        "media_type": "image/jpeg",
                        "data":       base64.b64encode(f.read()).decode(),
                    })
                extracted_ts.append(ts)

        # Strip audio and transcribe
        audio_path = os.path.join(tmp, "audio.mp3")
        subprocess.run(
            ["ffmpeg", "-i", path, "-vn", "-ar", "16000", "-ac", "1", "-q:a", "5", "-y", audio_path],
            capture_output=True, timeout=60,
        )
        transcript = _transcribe(audio_path)

    # Build the text block that appears alongside the frames
    mins, secs = int(duration // 60), int(duration % 60)
    ts_str     = ", ".join(f"{t:.1f}s" for t in extracted_ts)
    text       = f"Video: {title}\nDuration: {mins}:{secs:02d}\nFrames: {len(frame_list)} extracted at [{ts_str}]\n"
    if transcript:
        text += f"\nTRANSCRIPT:\n{transcript}"
    else:
        text += "\n(No audio transcript — either no speech detected or Deepgram unavailable)"

    return {
        "__type": "video_content",
        "text":   text,
        "frames": frame_list,
    }


def _youtube_transcript(url: str) -> str:
    import re
    patterns = [
        r'[?&]v=([0-9A-Za-z_-]{11})',
        r'youtu\.be/([0-9A-Za-z_-]{11})',
        r'youtube\.com/embed/([0-9A-Za-z_-]{11})',
    ]
    video_id = None
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break
    if not video_id:
        return f"Could not extract video ID from URL: {url}"

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return (
            "youtube-transcript-api not installed. Ask Sam to run:\n"
            "  pip install youtube-transcript-api\nThen try again."
        )

    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = " ".join(s["text"] for s in segments)
        duration = (segments[-1]["start"] + segments[-1]["duration"]) if segments else 0
        mins, secs = int(duration // 60), int(duration % 60)
        word_count = len(full_text.split())
        return (
            f"YOUTUBE TRANSCRIPT\n"
            f"URL: {url}\n"
            f"Video ID: {video_id}\n"
            f"Duration: ~{mins}:{secs:02d}  |  Words: {word_count}\n\n"
            f"{full_text}"
        )
    except Exception as e:
        return (
            f"Could not get transcript for {url}: {e}\n\n"
            "Note: Some videos have captions disabled or are in an unsupported language. "
            "Try video_download + video_process instead to transcribe the audio directly."
        )


def handle(name: str, inputs: dict):
    if name == "youtube_transcript":
        return _youtube_transcript(inputs.get("url", ""))
    if name == "video_download":
        return _download(inputs.get("url", ""), inputs.get("output_name"))
    if name == "video_process":
        return _process(inputs.get("path", ""), inputs.get("frames", 10))
    return f"Unknown tool: {name}"
