import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)                            # TINA root → config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend/ → tina package

import asyncio
import base64
import json as _json
import re
from datetime import datetime
import httpx
import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from config import (
    ANTHROPIC_API_KEY, MODEL,
    DEEPGRAM_API_KEY, ELEVENLABS_API_KEY,
    DEFAULT_VOICE_ID, ELEVENLABS_MODEL, ELEVENLABS_FORMAT,
)
from tina.agent import TinaAgent

app = FastAPI(title="TINA Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: list[WebSocket] = []
agent = TinaAgent()
_hud_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

_HUD_SYSTEM = """You are TINA's neural core generating live dashboard intelligence panels.
Respond ONLY with a JSON array of 2-4 element specs. No markdown, no explanation, raw JSON only.

Each element has:
- title: string (uppercase, max 14 chars)
- persistent: boolean (true = stays until cleared)
- ephemeral: number (ms, 4000-8000) if NOT persistent — omit if persistent
- type: one of: agent_grid | thought | memory_nodes | data_flow | confidence | bars | alert

Type-specific fields:
- agent_grid: agents:[{name:string, active:boolean}] — 4 items, mix active/idle
- thought: thoughts:[string] — 3 short inner-monologue fragments, first person
- memory_nodes: nodes:[string] — 5-6 short topic tags from recent context
- data_flow: label:string, bps:string (e.g. "2.4 KB/s")
- confidence: value:number (0-100), label:string
- bars: bars:[{label:string, value:number}] — 3 items, 0-100
- alert: message:string, level:"info"|"warn"|"error"

Mix persistent and ephemeral. Be creative and AI-system-appropriate."""


async def broadcast(data: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm;codecs=opus") -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.deepgram.com/v1/listen",
            params={
                "model":        "nova-2",
                "language":     "en-AU",
                "smart_format": "true",
                "punctuate":    "true",
            },
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type":  mime_type,
            },
            content=audio_bytes,
        )
        if not r.is_success:
            raise RuntimeError(f"Deepgram {r.status_code}: {r.text[:200]}")
        result = r.json()
        return result["results"]["channels"][0]["alternatives"][0]["transcript"]


async def synthesise(text: str) -> bytes | None:
    if not ELEVENLABS_API_KEY or not text.strip():
        return None
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{DEFAULT_VOICE_ID}",
            params={"output_format": ELEVENLABS_FORMAT},
            headers={
                "xi-api-key":   ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={"text": text, "model_id": ELEVENLABS_MODEL},
        )
        if r.status_code == 200:
            return r.content
        return None


_AGENT_META = {
    "research": {"display": "Research", "color": "#06b6d4", "glow": "#67e8f9"},
    "coding":   {"display": "Coding",   "color": "#10b981", "glow": "#6ee7b7"},
}


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


async def _tts_stream(reply: str):
    """Split reply into sentences, TTS each one, broadcast as indexed chunks."""
    if not ELEVENLABS_API_KEY:
        await broadcast({"type": "audio_end"})
        return
    sentences = [s.strip() for s in _SENTENCE_RE.split(reply) if s.strip()]
    if not sentences:
        sentences = [reply.strip()]
    await broadcast({"type": "state", "state": "speaking"})
    for i, sentence in enumerate(sentences):
        audio = await synthesise(sentence)
        if audio:
            await broadcast({
                "type":  "audio_chunk",
                "index": i,
                "data":  base64.b64encode(audio).decode(),
            })
    await broadcast({"type": "audio_end"})


async def _handle_message(text: str):
    """Shared logic for text input from both voice (STT) and typed messages."""
    await broadcast({"type": "state", "state": "thinking"})

    async def on_tool(name: str, inputs: dict = None):
        if name == "delegate_to_agent":
            key  = (inputs or {}).get("agent", "")
            meta = _AGENT_META.get(key, {"display": key.capitalize(), "color": "#8B5CF6", "glow": "#A78BFA"})
            await broadcast({"type": "agent_active", "agent": meta["display"], "color": meta["color"], "glow": meta["glow"]})
        else:
            await broadcast({"type": "tool", "name": name, "time": datetime.now().strftime("%H:%M:%S")})

    async def on_agent_done(agent_key: str):
        await broadcast({"type": "agent_done"})

    reply = await agent.chat(text, on_tool=on_tool, on_agent_done=on_agent_done)
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply))  # background — non-blocking
    await _tts_stream(reply)


async def _write_memory(user_msg: str, tina_reply: str) -> None:
    from tina.memory import extract_and_write_notes
    await extract_and_write_notes(user_msg, tina_reply)


@app.post("/api/spawn-hud")
async def spawn_hud():
    response = await _hud_client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=_HUD_SYSTEM,
        messages=[{"role": "user", "content": "Generate HUD elements now."}],
    )
    text = response.content[0].text.replace("```json", "").replace("```", "").strip()
    return _json.loads(text)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    await ws.send_json({"type": "state", "state": "listening"})
    pending_mime = "audio/webm;codecs=opus"  # updated by audio_meta message
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            # ── Binary frame: audio from browser mic ──────────────────────────
            if msg.get("bytes"):
                audio_bytes = msg["bytes"]
                print(f"[STT] received {len(audio_bytes)} bytes, mime={pending_mime}")
                if len(audio_bytes) < 512:
                    print("[STT] audio too short, ignoring")
                    await broadcast({"type": "state", "state": "listening"})
                    continue
                try:
                    transcript = await transcribe_audio(audio_bytes, pending_mime)
                    print(f"[STT] transcript: {repr(transcript)}")
                    if transcript.strip():
                        await broadcast({"type": "heard", "text": transcript})
                        await _handle_message(transcript)
                    else:
                        await broadcast({"type": "state", "state": "listening"})
                except Exception as e:
                    print(f"[STT] error: {e}")
                    await broadcast({"type": "response", "text": f"[STT error: {e}]"})
                    await broadcast({"type": "state", "state": "listening"})

            # ── Text frame: JSON control messages ─────────────────────────────
            elif msg.get("text"):
                data = _json.loads(msg["text"])
                msg_type = data.get("type")

                if msg_type == "audio_meta":
                    pending_mime = data.get("mimeType", pending_mime)
                    print(f"[STT] mime type set to: {pending_mime}")

                elif msg_type == "message":
                    text = data.get("text", "").strip()
                    if not text:
                        continue
                    await broadcast({"type": "heard", "text": text})
                    await _handle_message(text)

                elif msg_type == "audio_done":
                    await broadcast({"type": "state", "state": "listening"})

                elif msg_type == "reset":
                    agent.reset()

    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)
