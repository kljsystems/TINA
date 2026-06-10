"""Run this once to authenticate Google Calendar and save token.json."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calendar_tool import _service

svc = _service()
if svc:
    print("Auth successful. token.json saved.")
    events = svc.events().list(calendarId="primary", maxResults=3, singleEvents=True, orderBy="startTime").execute()
    items = events.get("items", [])
    print(f"Verified — {len(items)} upcoming event(s) visible.")
else:
    print("Auth failed — check credentials.json exists.")
