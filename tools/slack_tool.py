"""TINA Tool — Slack (send messages, read history)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import SLACK_BOT_TOKEN, SLACK_CHANNEL
except Exception:
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_CHANNEL   = os.getenv("SLACK_CHANNEL", "#tina")

DEFINITIONS = [
    {
        "name": "slack_send",
        "description": (
            "Send a message to Kai via Slack. Use for async updates, summaries, "
            "reminders, or anything that doesn't need an immediate voice/dashboard response. "
            "Prefer Slack when Kai is likely away from the dashboard."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message text to send."},
                "channel": {"type": "string", "description": "Channel name or ID. Defaults to configured channel."},
            },
            "required": ["message"],
        },
    },
    {
        "name": "slack_history",
        "description": "Read recent messages from a Slack channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name or ID. Defaults to configured channel."},
                "limit":   {"type": "integer", "description": "Number of messages to fetch (default 10, max 50)."},
            },
            "required": [],
        },
    },
]


def _client():
    from slack_sdk import WebClient
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN not set in .env")
    return WebClient(token=SLACK_BOT_TOKEN)


def _resolve_channel(channel: str | None) -> str:
    ch = channel or SLACK_CHANNEL or "#tina"
    return ch if ch.startswith("#") or ch.startswith("C") else f"#{ch}"


def handle(name: str, inputs: dict) -> str:
    try:
        client  = _client()
        channel = _resolve_channel(inputs.get("channel"))

        if name == "slack_send":
            msg = inputs.get("message", "").strip()
            if not msg:
                return "No message provided."
            client.chat_postMessage(channel=channel, text=msg)
            return f"Message sent to {channel}."

        elif name == "slack_history":
            limit = min(int(inputs.get("limit", 10)), 50)
            resp  = client.conversations_history(channel=channel, limit=limit)
            msgs  = resp.get("messages", [])
            if not msgs:
                return f"No messages found in {channel}."
            lines = []
            for m in reversed(msgs):
                user = m.get("username") or m.get("bot_profile", {}).get("name") or m.get("user", "unknown")
                text = m.get("text", "").replace("\n", " ")
                lines.append(f"{user}: {text}")
            return f"Recent messages in {channel}:\n\n" + "\n".join(lines)

        return f"Unknown slack tool: {name}"

    except Exception as e:
        return f"Slack error: {e}"
