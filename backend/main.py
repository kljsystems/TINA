import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)                            # TINA root → config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # backend/ → tina package

import asyncio
import base64
import json as _json
import re
from contextlib import asynccontextmanager
from datetime import datetime
import httpx
import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from config import (
    ANTHROPIC_API_KEY, MODEL, ORCHESTRATOR_MODEL, SYSTEM_PROMPT,
    DEEPGRAM_API_KEY, ELEVENLABS_API_KEY,
    DEFAULT_VOICE_ID, ELEVENLABS_MODEL, ELEVENLABS_FORMAT,
    SLACK_TINA_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_SAM_BOT_TOKEN, SLACK_KAI_USER_ID, SLACK_SAM_USER_ID,
    SLACK_CHANNEL, SLACK_CHANNEL_SAM, SLACK_CHANNEL_RESEARCH, SLACK_CHANNEL_AGENTS,
)
from tina.agent import TinaAgent

_agent_lock = asyncio.Lock()

_AGENT_META = {
    "research": {"display": "Research", "color": "#06b6d4", "glow": "#67e8f9", "channel": SLACK_CHANNEL_RESEARCH, "token": None},
    "coding":   {"display": "Sam",      "color": "#10b981", "glow": "#6ee7b7", "channel": SLACK_CHANNEL_SAM,      "token": SLACK_SAM_BOT_TOKEN or None},
}

# Channel → agent key, for routing direct Slack messages to the right agent
_CHANNEL_TO_AGENT = {
    SLACK_CHANNEL_SAM:      "coding",
    SLACK_CHANNEL_RESEARCH: "research",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_start_slack())
    yield


app = FastAPI(title="TINA Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connections: list[WebSocket] = []

# Per-agent queues for Ky's direct replies in agent channels
_agent_answer_queues: dict[str, asyncio.Queue] = {}
_channel_name_cache:  dict[str, str]           = {}  # channel ID → "#name"


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


# ── Background agent runner ───────────────────────────────────────────────────

def _make_slack_client(token: str | None = None):
    from slack_sdk import WebClient
    return WebClient(token=token or SLACK_TINA_BOT_TOKEN)


async def _slack_post(channel: str, message: str, token: str | None = None):
    """Post to Slack using the provided token (agent-specific) or fall back to Tina's token."""
    def _post():
        _make_slack_client(token).chat_postMessage(channel=channel, text=message)
    try:
        await asyncio.to_thread(_post)
    except Exception as e:
        print(f"[Slack] post to {channel} failed: {e}")


async def _resolve_channel_name(channel_id: str) -> str:
    """Resolve a Slack channel ID to its #name, with caching."""
    if channel_id in _channel_name_cache:
        return _channel_name_cache[channel_id]
    try:
        def _fetch():
            from slack_sdk import WebClient
            info = WebClient(token=SLACK_TINA_BOT_TOKEN).conversations_info(channel=channel_id)
            return "#" + info["channel"]["name"]
        name = await asyncio.to_thread(_fetch)
        _channel_name_cache[channel_id] = name
        return name
    except Exception:
        return channel_id


async def _get_tina_answer(question: str) -> str:
    """Answer a clarifying question from an agent using Tina's current conversation context."""
    try:
        client   = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        messages = list(agent.history) + [{
            "role":    "user",
            "content": (
                f"One of your specialist agents has a clarifying question:\n\n{question}\n\n"
                "Answer directly and concisely. If you genuinely don't know, say so and tell the agent to use its best judgement."
            ),
        }]
        response = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return next((b.text for b in response.content if hasattr(b, "text")), "")
    except Exception as e:
        print(f"[_get_tina_answer] error: {e}")
        return "I couldn't get a clear answer right now — use your best judgement and proceed."


_ESCALATE_SYSTEM = """You decide whether an agent's question requires the user's direct input or can be answered automatically.

Respond with exactly one word: ESCALATE or AUTO.

ESCALATE for:
- Deleting or overwriting files, data, or records
- Sending messages, emails, or notifications to external people
- Financial transactions or purchases
- Pushing to production, merging PRs, deploying
- Any action that cannot be easily undone
- Anything that affects people outside this system

AUTO for:
- Code architecture and design decisions
- UI/UX style and preference choices
- Technical stack or library choices
- File naming, structure, organisation
- Anything easily reversible
- Anything Tina can determine from user history and preferences"""


async def _should_escalate_to_kai(question: str) -> bool:
    """Return True if this question needs Ky's direct input rather than Tina's auto-answer."""
    try:
        client   = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=10,
            system=_ESCALATE_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        text = next((b.text for b in response.content if hasattr(b, "text")), "AUTO")
        return "ESCALATE" in text.upper()
    except Exception as e:
        print(f"[escalate] classification error: {e}")
        return False  # default to auto on error


async def background_runner(agent_key: str, cls, task: str, on_tool):
    """Called by TinaAgent._dispatch — launches specialist as a fire-and-forget task."""
    asyncio.create_task(_run_agent_background(agent_key, cls, task, on_tool))


async def _run_agent_background(agent_key: str, cls, task: str, on_tool):
    """Runs a specialist agent independently with Slack as the conversation channel."""
    meta         = _AGENT_META.get(agent_key, {"display": agent_key, "color": "#8B5CF6", "glow": "#A78BFA", "channel": SLACK_CHANNEL, "token": None})
    display      = meta["display"]
    channel      = meta.get("channel", SLACK_CHANNEL)
    agent_token  = meta.get("token")   # agent's own Slack token (e.g. Sam's)
    tina_token   = SLACK_TINA_BOT_TOKEN     # Tina always posts as herself

    # Tina posts the task brief
    await _slack_post(channel, f"*Task from Tina:*\n\n{task}", token=tina_token)

    async def question_handler(question: str) -> str:
        # Sam posts his question as himself
        await _slack_post(channel, question, token=agent_token)

        # Classify: can Tina handle this, or does Ky need to decide?
        escalate, tina_answer = await asyncio.gather(
            _should_escalate_to_kai(question),
            _get_tina_answer(question),
        )

        if not escalate:
            # Low-stakes — Tina answers immediately, Sam never waits
            await _slack_post(channel, tina_answer, token=tina_token)
            return tina_answer

        # High-stakes — park the task and wait for Ky
        kai_mention = f"<@{SLACK_KAI_USER_ID}>" if SLACK_KAI_USER_ID else "Ky"
        await _slack_post(
            channel,
            f"[ACTION REQUIRED] {kai_mention} — I need your call on this. Sam will wait.\n\n"
            f"_Tina's suggestion if you're unavailable: {tina_answer}_",
            token=tina_token,
        )

        q: asyncio.Queue = asyncio.Queue()
        _agent_answer_queues[channel] = q
        try:
            # Wait up to 4 hours for Ky — task is parked, not timed out
            kai_answer = await asyncio.wait_for(q.get(), timeout=14400)
            await _slack_post(channel, "Got it, thanks.", token=agent_token)
            return kai_answer
        except asyncio.TimeoutError:
            await _slack_post(
                channel,
                "No response after 4 hours — proceeding with Tina's suggestion.",
                token=agent_token,
            )
            return tina_answer
        finally:
            _agent_answer_queues.pop(channel, None)

    try:
        print(f"[{display}] background task started: {task[:80]}...")
        specialist = cls()
        result     = await specialist.run(task, on_tool=on_tool, question_handler=question_handler)

        summary = result[:300] + "…" if len(result) > 300 else result
        print(f"[{display}] background task complete ({len(result)} chars)")

        # Sam posts his own result
        full_msg = result[:2000] + (f"\n_(truncated — {len(result):,} chars total)_" if len(result) > 2000 else "")
        await _slack_post(channel, full_msg, token=agent_token)

        # Tina pings #tina so Ky sees it without having to check #sam
        await _slack_post(SLACK_CHANNEL, f"*{display} just finished.* Full result in {channel}.\n\n_{summary}_", token=tina_token)

        # Dashboard update
        await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": summary})
        await broadcast({"type": "response", "text": f"{display} finished — check {channel} in Slack"})
        asyncio.create_task(_tts_stream(f"{display} just finished. Check {channel} in Slack for the result."))

    except Exception as e:
        print(f"[{display}] background task error: {e}")
        await _slack_post(channel, f"Hit an error: {e}", token=agent_token)
        await broadcast({"type": "agent_background_done", "agent": agent_key, "display": display, "summary": f"Error: {e}"})
        await broadcast({"type": "response", "text": f"{display} hit an error: {e}"})


async def _direct_agent_chat(agent_key: str, text: str, channel: str):
    """Handle a direct message to an agent in their Slack channel."""
    from tina.agent import _AGENTS
    meta        = _AGENT_META.get(agent_key, {})
    agent_token = meta.get("token")
    cls         = _AGENTS.get(agent_key)
    if not cls:
        return
    try:
        specialist = cls()
        result     = await specialist.run(text)
        await _slack_post(channel, result[:2000], token=agent_token)
        if len(result) > 2000:
            await _slack_post(channel, f"_(response truncated — {len(result):,} chars total)_", token=agent_token)
    except Exception as e:
        await _slack_post(channel, f"Error: {e}", token=agent_token)


# ── Agent instance (wired with background runner) ─────────────────────────────
agent      = TinaAgent(background_runner=background_runner)
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


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


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
            # Background mode: agent runs independently — use agent_background_start not agent_active
            event_type = "agent_background_start" if agent.has_background_runner else "agent_active"
            await broadcast({
                "type":  event_type,
                "agent": meta["display"],
                "key":   key,
                "color": meta["color"],
                "glow":  meta["glow"],
            })
        else:
            await broadcast({"type": "tool", "name": name, "time": datetime.now().strftime("%H:%M:%S")})

    async def on_agent_done(agent_key: str):
        # Only called in blocking (non-background) mode
        await broadcast({"type": "agent_done"})

    reply = await agent.chat(text, on_tool=on_tool, on_agent_done=on_agent_done, background=True)
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply))
    await _tts_stream(reply)


async def _write_memory(user_msg: str, tina_reply: str) -> None:
    from tina.memory import extract_and_write_notes
    await extract_and_write_notes(user_msg, tina_reply)


@app.get("/api/status")
async def get_status():
    from config import DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, GITHUB_TOKEN, TAVILY_API_KEY, OPENWEATHER_API_KEY
    return {
        "deepgram":    bool(DEEPGRAM_API_KEY),
        "elevenlabs":  bool(ELEVENLABS_API_KEY),
        "github":      bool(GITHUB_TOKEN),
        "tavily":      bool(TAVILY_API_KEY),
        "weather":     bool(OPENWEATHER_API_KEY),
    }


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


@app.post("/api/chat")
async def chat_endpoint(body: dict):
    """Shared chat entry point used by Slack and any other async callers."""
    text   = body.get("text", "").strip()
    source = body.get("source", "api")
    if not text:
        return {"reply": ""}
    label = f"[{source.upper()}] {text}"
    await broadcast({"type": "heard", "text": label})
    async with _agent_lock:
        # background=False: Slack waits for the full reply including any delegation
        reply = await agent.chat(text, background=False)
    await broadcast({"type": "response", "text": reply})
    asyncio.create_task(_write_memory(text, reply))
    asyncio.create_task(_tts_stream(reply))
    return {"reply": reply}


async def _start_slack():
    if not SLACK_TINA_BOT_TOKEN or not SLACK_APP_TOKEN:
        print("[Slack] Tokens not configured — Slack listener not started.")
        return
    try:
        from slack_bolt.async_app import AsyncApp as BoltApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        import httpx as _httpx

        bolt = BoltApp(token=SLACK_TINA_BOT_TOKEN)

        @bolt.message("")
        async def on_message(message, say, logger):
            text = message.get("text", "").strip()
            if not text or message.get("bot_id"):
                return

            # Resolve channel ID to name
            channel_id   = message.get("channel", "")
            channel_name = await _resolve_channel_name(channel_id)

            # Agent is waiting for Ky's reply (escalated question)
            if channel_name in _agent_answer_queues:
                await _agent_answer_queues[channel_name].put(text)
                return

            # Direct message to an agent's own channel
            agent_key = _CHANNEL_TO_AGENT.get(channel_name)
            if agent_key:
                asyncio.create_task(_direct_agent_chat(agent_key, text, channel_name))
                return

            # Otherwise route to Tina
            try:
                async with _httpx.AsyncClient(timeout=120) as client:
                    r = await client.post(
                        "http://localhost:8000/api/chat",
                        json={"text": text, "source": "slack"},
                    )
                reply = r.json().get("reply", "")
                if reply:
                    await say(reply)
            except Exception as e:
                logger.error(f"Slack handler error: {e}")
                await say(f"Error: {e}")

        handler = AsyncSocketModeHandler(bolt, SLACK_APP_TOKEN)
        print("[Slack] Socket Mode listener starting...")
        await handler.start_async()
    except Exception as e:
        print(f"[Slack] Failed to start: {e}")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    await ws.send_json({"type": "state", "state": "listening"})
    pending_mime = "audio/webm;codecs=opus"
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
                data     = _json.loads(msg["text"])
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
