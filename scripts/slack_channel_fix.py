"""
Diagnose Slack channel membership for all TINA bots.
Run: python scripts/slack_channel_fix.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from slack_sdk import WebClient

BOTS = {
    "TINA":    os.getenv("SLACK_TINA_BOT_TOKEN",    ""),
    "SAM":     os.getenv("SLACK_SAM_BOT_TOKEN",      ""),
    "TRISTAN": os.getenv("SLACK_TRISTAN_BOT_TOKEN",  ""),
    "CHARLIE": os.getenv("SLACK_CHARLIE_BOT_TOKEN",  ""),
    "CONNOR":  os.getenv("SLACK_CONNOR_BOT_TOKEN",   ""),
    "WADE":    os.getenv("SLACK_WADE_BOT_TOKEN",     ""),
}

TARGETS = {
    "SLACK_CHANNEL":          (os.getenv("SLACK_CHANNEL",          ""), ["TINA"]),
    "SLACK_CHANNEL_SAM":      (os.getenv("SLACK_CHANNEL_SAM",      ""), ["TINA", "SAM"]),
    "SLACK_CHANNEL_RESEARCH": (os.getenv("SLACK_CHANNEL_RESEARCH", ""), ["TINA", "CHARLIE"]),
    "SLACK_CHANNEL_TRISTAN":  (os.getenv("SLACK_CHANNEL_TRISTAN",  ""), ["TINA", "TRISTAN"]),
    "SLACK_CHANNEL_CONNOR":   (os.getenv("SLACK_CHANNEL_CONNOR",   ""), ["TINA", "CONNOR"]),
    "SLACK_CHANNEL_AGENTS":   (os.getenv("SLACK_CHANNEL_AGENTS",   ""), ["TINA"]),
    "SLACK_CHANNEL_WADE":     (os.getenv("SLACK_CHANNEL_WADE",     ""), ["TINA", "WADE"]),
}

_channel_cache = {}

def get_channel_info(label, token, channel_val):
    """Look up channel info by ID or name."""
    cache_key = f"{label}:{channel_val}"
    if cache_key in _channel_cache:
        return _channel_cache[cache_key]
    if not token or not channel_val:
        return None
    try:
        c = WebClient(token=token)
        # If it looks like a channel ID, use conversations_info
        if channel_val.startswith(("C", "G", "D")):
            resp = c.conversations_info(channel=channel_val)
            ch = resp["channel"]
            result = {"id": ch["id"], "name": ch["name"], "is_member": ch.get("is_member", False)}
        else:
            # Name-based lookup via conversations_list
            name = channel_val.lstrip("#")
            resp = c.conversations_list(types="public_channel", limit=200)
            ch = next((x for x in resp["channels"] if x["name"] == name), None)
            if not ch:
                result = None
            else:
                result = {"id": ch["id"], "name": ch["name"], "is_member": ch.get("is_member", False)}
        _channel_cache[cache_key] = result
        return result
    except Exception as e:
        _channel_cache[cache_key] = None
        return None

print("=" * 70)
print("TINA Slack Channel Audit")
print("=" * 70)

missing = []

for env_key, (channel_val, required_bots) in TARGETS.items():
    if not channel_val:
        print(f"\n{env_key} = (not set)")
        continue

    print(f"\n{env_key} = {channel_val}")

    channel_id   = None
    channel_name = None

    for label, token in BOTS.items():
        if not token:
            continue
        info = get_channel_info(label, token, channel_val)
        if info:
            channel_id   = info["id"]
            channel_name = info["name"]
            is_member    = info["is_member"]
            status       = "OK member" if is_member else "NOT member"
            flag         = " <-- needs invite" if not is_member and label in required_bots else ""
            print(f"  [{label:8}] {status}  (#{channel_name}, id={channel_id}){flag}")
            if not is_member and label in required_bots:
                missing.append((label.lower(), channel_name))
        else:
            if label in required_bots:
                print(f"  [{label:8}] could not check")

print("\n" + "=" * 70)
if missing:
    print("ACTION REQUIRED — run these in Slack:")
    for bot, ch in missing:
        print(f"  In #{ch}: /invite @{bot}")
else:
    print("All required bots are members of their channels.")
print("=" * 70)
