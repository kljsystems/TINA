"""
media_tool.py — Charlie's media downloader.
Downloads images and videos from direct URLs and saves them to the
Charlie media folder (inside Generated Docs) so Ky can view them.

Pure stdlib (urllib) — no extra pip deps. Downloads DIRECT media URLs only;
it does not rip YouTube/streaming pages (that needs yt-dlp — follow-up if wanted).
"""
import os
import sys
import re
import mimetypes
import urllib.request
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CHARLIE_MEDIA_DIR

# Safety caps
_MAX_BYTES = 200 * 1024 * 1024   # 200 MB hard ceiling
_TIMEOUT   = 30                  # seconds
_UA        = "TINA-Charlie/1.0 (+https://kljsystems.com.au)"

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/svg+xml", "image/tiff"}
_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/mpeg"}

_EXT_FROM_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/svg+xml": ".svg",
    "image/tiff": ".tiff", "video/mp4": ".mp4", "video/webm": ".webm",
    "video/quicktime": ".mov", "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv", "video/mpeg": ".mpeg",
}


DEFINITIONS = [
    {
        "name": "save_media",
        "description": (
            "Download an image or video from a direct URL and save it to Ky's Charlie "
            "media folder so he can view it. Use this for relevant images or videos found "
            "during research. The URL must point directly at the media file "
            "(e.g. ends in .jpg, .png, .mp4) — not a webpage containing it. "
            "Returns the saved file path. Streaming pages (YouTube etc.) are not supported."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Direct URL to the image or video file.",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Optional descriptive filename without extension "
                        "(e.g. 'sydney-harbour-bridge'). Extension is inferred from content type."
                    ),
                },
            },
            "required": ["url"],
        },
    }
]


def handle(name: str, inputs: dict) -> str:
    if name == "save_media":
        return _save_media(inputs.get("url", ""), inputs.get("filename", ""))
    return f"Unknown tool: {name}"


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:60] or "media"


def _ensure_dir() -> str:
    os.makedirs(CHARLIE_MEDIA_DIR, exist_ok=True)
    return CHARLIE_MEDIA_DIR


def _save_media(url: str, filename: str) -> str:
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return f"Invalid URL: {url!r}. Must start with http:// or https://."

    folder = _ensure_dir()
    req = urllib.request.Request(url, headers={"User-Agent": _UA})

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            ctype = (resp.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()

            is_image = ctype in _IMAGE_TYPES
            is_video = ctype in _VIDEO_TYPES

            # Fall back to URL extension if content-type is generic/missing
            if not (is_image or is_video):
                guessed, _ = mimetypes.guess_type(urllib.parse.urlparse(url).path)
                if guessed in _IMAGE_TYPES:
                    ctype, is_image = guessed, True
                elif guessed in _VIDEO_TYPES:
                    ctype, is_video = guessed, True

            if not (is_image or is_video):
                return (
                    f"URL did not return an image or video (Content-Type: {ctype or 'unknown'}). "
                    "Make sure the URL points directly at a media file."
                )

            length = resp.headers.get("Content-Length")
            if length and int(length) > _MAX_BYTES:
                return f"File too large ({int(length) // (1024*1024)} MB). Limit is {_MAX_BYTES // (1024*1024)} MB."

            # Build filename
            url_ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
            ext     = _EXT_FROM_TYPE.get(ctype, url_ext or ".bin")
            if filename:
                base = _slugify(filename)
            else:
                url_base = os.path.splitext(os.path.basename(urllib.parse.urlparse(url).path))[0]
                base     = _slugify(url_base) if url_base else "media"
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path  = os.path.join(folder, f"{base}-{stamp}{ext}")

            # Stream to disk with size cap enforced as we read
            written = 0
            with open(path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_BYTES:
                        f.close()
                        os.remove(path)
                        return f"Aborted — file exceeded {_MAX_BYTES // (1024*1024)} MB limit during download."
                    f.write(chunk)

    except Exception as e:
        return f"Failed to download media from {url}: {e}"

    kind = "image" if is_image else "video"
    size_kb = written // 1024
    return f"Saved {kind} ({size_kb} KB) to {path}"
