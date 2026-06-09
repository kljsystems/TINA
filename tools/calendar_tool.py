"""TINA Tool — Google Calendar"""
import os
import datetime
from config import CREDENTIALS_FILE, TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFINITIONS = [
    {"name":"list_events","description":"List upcoming calendar events. Use for schedule, appointments, what's on today/this week.","input_schema":{"type":"object","properties":{"time_min":{"type":"string"},"time_max":{"type":"string"},"max_results":{"type":"integer"},"query":{"type":"string"}},"required":[]}},
    {"name":"create_event","description":"Create a new calendar event.","input_schema":{"type":"object","properties":{"title":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},"location":{"type":"string"},"description":{"type":"string"}},"required":["title","start"]}},
    {"name":"update_event","description":"Update an existing calendar event by ID.","input_schema":{"type":"object","properties":{"event_id":{"type":"string"},"title":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},"location":{"type":"string"},"description":{"type":"string"}},"required":["event_id"]}},
    {"name":"delete_event","description":"Delete a calendar event. Always confirm before deleting.","input_schema":{"type":"object","properties":{"event_id":{"type":"string"}},"required":["event_id"]}},
    {"name":"check_availability","description":"Check if a time slot is free.","input_schema":{"type":"object","properties":{"start":{"type":"string"},"end":{"type":"string"}},"required":["start","end"]}},
]

def _service():
    import warnings; warnings.filterwarnings("ignore")
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE,"w") as f:
            f.write(creds.to_json())
    return build("calendar","v3",credentials=creds)

def _parse_dt(s):
    for fmt in ["%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M","%Y-%m-%d %H:%M:%S","%Y-%m-%d","%d/%m/%Y %H:%M","%d/%m/%Y"]:
        try: return datetime.datetime.strptime(s.strip(), fmt)
        except: pass
    return None

def _fmt(event):
    s = event.get("start",{})
    e = event.get("end",{})
    if "dateTime" in s:
        sd = datetime.datetime.fromisoformat(s["dateTime"])
        ed = datetime.datetime.fromisoformat(e["dateTime"])
        t = f"{sd.strftime('%A %d %B, %I:%M %p')} — {ed.strftime('%I:%M %p')}"
    else:
        sd = datetime.datetime.fromisoformat(s["date"])
        t = f"{sd.strftime('%A %d %B')} (all day)"
    lines = [f"{event.get('summary','Untitled')} | {t}"]
    if event.get("location"): lines.append(f"Where: {event['location']}")
    lines.append(f"ID: {event.get('id','')}")
    return "\n".join(lines)

def _tz():
    try:
        import tzlocal; return str(tzlocal.get_localzone())
    except: return "Australia/Sydney"

def handle(name: str, inputs: dict) -> str:
    try:
        svc = _service()
        if not svc: return "Google Calendar not configured."

        if name == "list_events":
            now = datetime.datetime.utcnow()
            t_min = (_parse_dt(inputs["time_min"]) or now).isoformat()+"Z" if inputs.get("time_min") else now.isoformat()+"Z"
            params = {"calendarId":"primary","timeMin":t_min,"maxResults":inputs.get("max_results",10),"singleEvents":True,"orderBy":"startTime"}
            if inputs.get("time_max"):
                dt = _parse_dt(inputs["time_max"])
                if dt: params["timeMax"] = dt.isoformat()+"Z"
            if inputs.get("query"): params["q"] = inputs["query"]
            events = svc.events().list(**params).execute().get("items",[])
            if not events: return "No events found."
            return "\n\n".join(_fmt(e) for e in events)

        elif name == "create_event":
            tz = _tz()
            sd = _parse_dt(inputs.get("start",""))
            if not sd: return "Couldn't parse start time."
            ed = _parse_dt(inputs.get("end","")) or sd + datetime.timedelta(hours=1)
            body = {"summary":inputs.get("title","Untitled"),"start":{"dateTime":sd.isoformat(),"timeZone":tz},"end":{"dateTime":ed.isoformat(),"timeZone":tz}}
            if inputs.get("location"): body["location"] = inputs["location"]
            if inputs.get("description"): body["description"] = inputs["description"]
            created = svc.events().insert(calendarId="primary",body=body).execute()
            return f"Event created: {_fmt(created)}"

        elif name == "update_event":
            event = svc.events().get(calendarId="primary",eventId=inputs["event_id"]).execute()
            tz = _tz()
            if inputs.get("title"): event["summary"] = inputs["title"]
            if inputs.get("location"): event["location"] = inputs["location"]
            if inputs.get("description"): event["description"] = inputs["description"]
            if inputs.get("start"):
                dt = _parse_dt(inputs["start"])
                if dt: event["start"] = {"dateTime":dt.isoformat(),"timeZone":tz}
            if inputs.get("end"):
                dt = _parse_dt(inputs["end"])
                if dt: event["end"] = {"dateTime":dt.isoformat(),"timeZone":tz}
            updated = svc.events().update(calendarId="primary",eventId=inputs["event_id"],body=event).execute()
            return f"Event updated: {_fmt(updated)}"

        elif name == "delete_event":
            event = svc.events().get(calendarId="primary",eventId=inputs["event_id"]).execute()
            title = event.get("summary","Untitled")
            svc.events().delete(calendarId="primary",eventId=inputs["event_id"]).execute()
            return f"Deleted event: {title}"

        elif name == "check_availability":
            sd = _parse_dt(inputs.get("start",""))
            ed = _parse_dt(inputs.get("end",""))
            if not sd or not ed: return "Couldn't parse time range."
            result = svc.freebusy().query(body={"timeMin":sd.isoformat()+"+10:00","timeMax":ed.isoformat()+"+10:00","items":[{"id":"primary"}]}).execute()
            busy = result.get("calendars",{}).get("primary",{}).get("busy",[])
            if not busy:
                return f"You are free between {sd.strftime('%I:%M %p')} and {ed.strftime('%I:%M %p')} on {sd.strftime('%A %d %B')}."
            conflicts = [f"{datetime.datetime.fromisoformat(b['start'].replace('Z','')).strftime('%I:%M %p')} — {datetime.datetime.fromisoformat(b['end'].replace('Z','')).strftime('%I:%M %p')}" for b in busy]
            return "You are busy during that time. Conflicts: " + ", ".join(conflicts)

    except Exception as e:
        return f"Calendar error: {e}"