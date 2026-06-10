"""Diagnose Google Calendar integration."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TOKEN_FILE, CREDENTIALS_FILE

print(f"credentials.json : {'EXISTS' if os.path.exists(CREDENTIALS_FILE) else 'MISSING'} → {CREDENTIALS_FILE}")
print(f"token.json       : {'EXISTS' if os.path.exists(TOKEN_FILE) else 'MISSING'} → {TOKEN_FILE}")
print()

try:
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, ["https://www.googleapis.com/auth/calendar"])
    print(f"Token valid      : {creds.valid}")
    print(f"Token expired    : {creds.expired}")
    print(f"Has refresh token: {bool(creds.refresh_token)}")
    print(f"Scopes           : {creds.scopes}")
    print()
except Exception as e:
    print(f"Token load error: {e}\n")
    sys.exit(1)

try:
    from tools.calendar_tool import _service
    svc = _service()
    if not svc:
        print("ERROR: _service() returned None — check credentials.json")
        sys.exit(1)

    # Which calendar are we hitting?
    cal = svc.calendars().get(calendarId="primary").execute()
    print(f"Calendar ID      : {cal.get('id')}")
    print(f"Calendar summary : {cal.get('summary')}")
    print()

    # List upcoming events
    import datetime
    now = datetime.datetime.utcnow().isoformat() + "Z"
    result = svc.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=5,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    items = result.get("items", [])
    print(f"Upcoming events  : {len(items)}")
    for e in items:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        print(f"  - {e.get('summary', 'Untitled')} @ {start}")

    if not items:
        print("  (no upcoming events found on primary calendar)")

    # Test write access — create then immediately delete a test event
    print()
    print("Testing write access...")
    import datetime as dt
    start = (dt.datetime.utcnow() + dt.timedelta(hours=1)).isoformat() + "Z"
    end   = (dt.datetime.utcnow() + dt.timedelta(hours=2)).isoformat() + "Z"
    try:
        created = svc.events().insert(calendarId="primary", body={
            "summary": "TINA DIAG TEST — safe to delete",
            "start": {"dateTime": start, "timeZone": "Australia/Sydney"},
            "end":   {"dateTime": end,   "timeZone": "Australia/Sydney"},
        }).execute()
        print(f"  Create OK → event ID: {created['id']}")
        svc.events().delete(calendarId="primary", eventId=created["id"]).execute()
        print(f"  Delete OK → write access confirmed")
    except Exception as e:
        print(f"  Write FAILED: {e}")

except Exception as e:
    print(f"Calendar API error: {e}")
