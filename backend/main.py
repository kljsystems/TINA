import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)                            # TINA root → config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend/ → tina package

import json as _json
import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from config import ANTHROPIC_API_KEY, MODEL
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
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "message":
                text = data.get("text", "").strip()
                if not text:
                    continue
                await broadcast({"type": "heard", "text": text})
                await broadcast({"type": "state", "state": "thinking"})
                reply = await agent.chat(text)
                await broadcast({"type": "response", "text": reply})
                await broadcast({"type": "state", "state": "listening"})
            elif data.get("type") == "reset":
                agent.reset()
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)
