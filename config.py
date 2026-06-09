"""
TINA — Central Configuration
All settings live here. Change things here, not in individual modules.
"""

import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
TAVILY_API_KEY      = os.getenv("TAVILY_API_KEY", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID       = os.getenv("GOOGLE_CSE_ID", "")
PICOVOICE_API_KEY   = os.getenv("PICOVOICE_API_KEY", "")

# ── AI Model ──────────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"

# ── Wake & Exit ───────────────────────────────────────────────────────────────
WAKE_WORDS        = ["hey tina", "tina"]
EXIT_COMMANDS     = ["goodbye tina", "exit", "quit", "shutdown"]

# ── Conversation ──────────────────────────────────────────────────────────────
CONVERSATION_TIMEOUT = 40   # seconds of silence before standby

# ── STT (Whisper) ─────────────────────────────────────────────────────────────
WHISPER_MODEL_SIZE = "small"
SAMPLE_RATE        = 16000
SILENCE_FRAMES     = 30     # ~3 seconds
SPEECH_FRAMES      = 3      # ~0.3s to start recording
MAX_RECORD_SEC     = 20
SILENCE_RMS        = 0.012
FRAME_MS           = 100

# ── TTS (ElevenLabs) ─────────────────────────────────────────────────────────
ELEVENLABS_MODEL   = "eleven_turbo_v2_5"
ELEVENLABS_FORMAT  = "mp3_44100_128"
DEFAULT_VOICE_ID   = "onwK4e9ZLuTAKqWW03F9"  # Daniel (free tier)

# ── File paths ────────────────────────────────────────────────────────────────
DATA_DIR        = os.path.join(BASE_DIR, "data")
VOICES_FILE     = os.path.join(DATA_DIR, "voices.json")
PREFS_FILE      = os.path.join(DATA_DIR, "prefs.json")
MEMORY_FILE     = os.path.join(DATA_DIR, "memory.json")
SUMMARIES_DIR   = os.path.join(DATA_DIR, "summaries")
STATUS_FILE     = os.path.join(DATA_DIR, "tina_status.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE      = os.path.join(DATA_DIR, "token.json")

# ── Default voices ────────────────────────────────────────────────────────────
DEFAULT_VOICES = [
    {"name": "Daniel",    "id": "onwK4e9ZLuTAKqWW03F9", "description": "British male, calm (free tier)"},
    {"name": "Matilda",   "id": "XrExE9yKIg1WjnnlVkGX", "description": "Australian female, warm"},
    {"name": "Hannah",    "id": "M7ya1YbaeFaPXljg9BpK", "description": "Australian female, natural"},
    {"name": "Charlotte", "id": "XB0fDUnXU5powFXDhCwa", "description": "British female, elegant"},
    {"name": "Liam",      "id": "TX3LPaxmHKxFdv7VOQHJ", "description": "Australian male, warm"},
    {"name": "Brian",     "id": "nPczCjzI2devNBz1zQrb", "description": "American male, deep"},
]

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are TINA (Totally Intelligent Neural Assistant), a highly capable female AI assistant.
You have a sharp, warm, confident, and occasionally sassy personality.
You address the user by their name if known, otherwise use casual friendly language.
You are helpful, precise, and efficient — never sycophantic or over-the-top.
Keep responses concise — 1-3 sentences for spoken replies unless asked for more detail.
Use dry humour when appropriate but never at the expense of being useful.
When you don't know something, use your tools to find out.
You have access to web search, weather, Wikipedia, and news — use them proactively for current or factual information.
Summarise tool results conversationally — never read out raw data or URLs.
You have a memory system — acknowledge important things the user tells you naturally.
You have access to the user's Google Calendar — check schedules, create, edit and delete events as asked.
Always confirm before deleting any event.
Use memory context provided to personalise your responses.
IMPORTANT: You are a voice assistant. Never use markdown formatting — no bold (**), italics (*), bullet points (-), headers (#), or any special characters. Speak in plain natural sentences only."""