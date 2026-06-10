import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)                            # TINA root → config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend/ → tina package

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
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
