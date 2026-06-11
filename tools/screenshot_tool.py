"""
Screenshot tool — lets Sam see the UI.
Returns a special dict that base.py converts into an image content block
so Claude's vision capability can analyse it.
"""
import base64
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_WIDTH = 1280  # resize to this width to keep token usage reasonable

DEFINITIONS = [
    {
        "name": "take_screenshot",
        "description": (
            "Take a screenshot of the screen and return it as an image you can see. "
            "Use this to visually inspect the Tina dashboard (localhost:5173), verify UI changes, "
            "diagnose layout issues, or check browser error states. "
            "Make sure the relevant window is visible on screen before calling this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "monitor": {
                    "type":        "integer",
                    "description": "Monitor number to capture (1 = primary, default). Use 0 for all monitors combined.",
                },
                "note": {
                    "type":        "string",
                    "description": "Optional context note — describe what you're looking for in this screenshot.",
                },
            },
            "required": [],
        },
    },
]


def handle(name: str, inputs: dict) -> dict | str:
    if name == "take_screenshot":
        return _take_screenshot(
            monitor=int(inputs.get("monitor", 1)),
            note=inputs.get("note", ""),
        )
    return f"Unknown tool: {name}"


def _take_screenshot(monitor: int = 1, note: str = "") -> dict | str:
    try:
        import mss
        import mss.tools
        from PIL import Image

        with mss.mss() as sct:
            monitors = sct.monitors  # [0] = all, [1] = primary, [2] = second...
            idx = max(0, min(monitor, len(monitors) - 1))
            raw = sct.grab(monitors[idx])

        # Convert to PIL image
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        # Resize if wider than MAX_WIDTH
        if img.width > MAX_WIDTH:
            ratio  = MAX_WIDTH / img.width
            height = int(img.height * ratio)
            img    = img.resize((MAX_WIDTH, height), Image.LANCZOS)

        # Encode to PNG base64
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = base64.standard_b64encode(buf.getvalue()).decode()

        prefix = f"Screenshot captured ({img.width}×{img.height}px)"
        if note:
            prefix += f" — looking for: {note}"

        # Return special dict — base.py detects this and builds an image content block
        return {
            "__type":     "image",
            "text":       prefix,
            "media_type": "image/png",
            "data":       data,
        }

    except ImportError as e:
        return f"Screenshot failed — missing library: {e}. Run: pip install mss Pillow"
    except Exception as e:
        return f"Screenshot failed: {e}"
