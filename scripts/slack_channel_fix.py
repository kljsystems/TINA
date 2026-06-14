"""
Diagnose Slack channel membership for all TINA bots and print channel ID fixes.
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
}

TARGETS = {
    "SLACK_CHANNEL":          (os.getenv("SLACK_CHANNEL",          "#tina").lstrip("#"),    ["TINA"]),
    "SLACK_CHANNEL_SAM":      (os.getenv("SLACK_CHANNEL_SAM",      "#sam").lstrip("#"),     ["TINA", "SAM"]),
    "SLACK_CHANNEL_RESEARCH": (os.getenv("SLACK_CHANNEL_RESEARCH", "#research").lstrip("#"),["TINA", "CHARLIE"]),
    "SLACK_CHANNEL_TRISTAN":  (os.getenv("SLACK_CHANNEL_TRISTAN",  "#email").lstrip("#"),   ["TINA", "TRISTAN"]),
    "SLACK_CHANNEL_CONNOR":   (os.getenv("SLACK_CHANNEL_CONNOR",   "#data").lstrip("#"),    ["TINA", "CONNOR"]),
    "SLACK_CHANNEL_AGENTS":   (os.getenv("SLACK_CHANNEL_AGENTS",   "#agents").lstrip("#"),  ["TINA"]),
}

# Cache membership per token
_membership = {}

def get_membership(label, token):
    if label in _membership:
        return _membership[label]
    if not token:
        _membership[label] = {}
        return {}
    try:
        c = WebClient(token=token)
        resp = c.conversations_list(types="public_channel", limit=200)
        result = {ch["name"]: ch for ch in resp["channels"]}
        _membership[label] = result
        return result
    except Exception as e:
        print(f"  [{label}] conversations_list failed: {e}")
        _membership[label] = {}
        return {}

print("=" * 70)
print("TINA Slack Channel Audit")
print("=" * 70)

fixes_needed = []

for env_key, (channel_name, required_bots) in TARGETS.items():
    current_val = os.getenv(env_key, f"#{channel_name}")
    print(f"\n#{channel_name}  ({env_key} = {current_val})")

    channel_id = None
    for label, token in BOTS.items():
        membership = get_membership(label, token)
        if channel_name in membership:
            ch = membership[channel_name]
            channel_id = ch["id"]
            is_member = ch.get("is_member", False)
            status = "✓ member" if is_member else "✗ NOT member"
            print(f"  [{label:8}] {status}  (id={ch['id']})")
        else:
            if token:
                print(f"  [{label:8}] channel not found in listing")

    if channel_id and not current_val.startswith("C") and not current_val.startswith("G"):
        fixes_needed.append((env_key, channel_id, channel_name))

print("\n" + "=" * 70)
if fixes_needed:
    print("Recommended .env fixes (use channel IDs for reliability):")
    for env_key, cid, name in fixes_needed:
        print(f"  {env_key}={cid}   # #{name}")
else:
    print("All channels already using IDs — no .env changes needed.")
print("=" * 70)
print("\nAction required: for any bot marked '✗ NOT member', run in Slack:")
print("  /invite @botname   (in the relevant channel)")
