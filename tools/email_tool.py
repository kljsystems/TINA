"""TINA Tool — Email (Tristan's send/read toolkit).

Three accounts:
  - personal         → kydanjenkins04@gmail.com   (Gmail API)
  - business_gmail   → kljsystems@gmail.com        (Gmail API)
  - business_outlook → kydan@kljsystems.com.au      (Microsoft Graph API)

Routing rules (enforced here AND in Tristan's system prompt):
  - personal emails       → always 'personal'
  - business emails       → default 'business_outlook' unless told otherwise
  - 'business_gmail'      → only when explicitly requested

Sending is irreversible. email_send REQUIRES confirmed=true, which Tristan
only sets after Ky has explicitly approved the final content.
"""
import os
import sys
import base64
import html
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import (
        GMAIL_PERSONAL_TOKEN, GMAIL_BUSINESS_TOKEN, GMAIL_CLIENT_SECRET_FILE,
        MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, MS_GRAPH_TENANT_ID,
        MS_GRAPH_TOKEN_FILE, OUTLOOK_SENDER,
    )
except Exception:
    GMAIL_PERSONAL_TOKEN     = os.getenv("GMAIL_PERSONAL_TOKEN", "")
    GMAIL_BUSINESS_TOKEN     = os.getenv("GMAIL_BUSINESS_TOKEN", "")
    GMAIL_CLIENT_SECRET_FILE = os.getenv("GMAIL_CLIENT_SECRET_FILE", "")
    MS_GRAPH_CLIENT_ID       = os.getenv("MS_GRAPH_CLIENT_ID", "")
    MS_GRAPH_CLIENT_SECRET   = os.getenv("MS_GRAPH_CLIENT_SECRET", "")
    MS_GRAPH_TENANT_ID       = os.getenv("MS_GRAPH_TENANT_ID", "")
    MS_GRAPH_TOKEN_FILE      = os.getenv("MS_GRAPH_TOKEN_FILE", "")
    OUTLOOK_SENDER           = os.getenv("OUTLOOK_SENDER", "kydan@kljsystems.com.au")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/contacts.readonly",
]

# account key → (provider, display address)
_ACCOUNTS = {
    "personal":         ("gmail",   "kydanjenkins04@gmail.com"),
    "business_gmail":   ("gmail",   "kljsystems@gmail.com"),
    "business_outlook": ("outlook", OUTLOOK_SENDER or "kydan@kljsystems.com.au"),
}

DEFINITIONS = [
    {
        "name": "contacts_search",
        "description": (
            "Search Ky's Google Contacts by name (or partial name) to look up an email address. "
            "Always call this BEFORE asking Ky for someone's email — if the contact exists you'll "
            "find it here. Returns name, email(s), and phone if available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name or partial name to search for (e.g. 'John', 'Smith', 'Dr Brown').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "email_list",
        "description": (
            "List recent emails from one of Ky's inboxes. Returns id, from, subject, date, "
            "short snippet, and read status. Use this to triage the inbox or find recent mail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                    "description": "Which account to check.",
                },
                "folder": {
                    "type": "string",
                    "enum": ["inbox", "sent", "drafts"],
                    "description": "Which folder to list. Defaults to inbox.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to return (1-50). Default 20.",
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "If true, only return unread emails.",
                },
            },
            "required": ["account"],
        },
    },
    {
        "name": "email_read",
        "description": (
            "Read the full content of a specific email by its ID (from email_list or email_search). "
            "Returns sender, recipients, subject, date, and full body text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                },
                "email_id": {
                    "type": "string",
                    "description": "The email ID returned by email_list or email_search.",
                },
                "mark_read": {
                    "type": "boolean",
                    "description": "If true, mark the email as read after fetching. Default false.",
                },
            },
            "required": ["account", "email_id"],
        },
    },
    {
        "name": "email_search",
        "description": (
            "Search emails in one of Ky's accounts using a text query. "
            "Supports Gmail search syntax (e.g. 'from:boss@co.com', 'subject:invoice', 'is:unread'). "
            "For Outlook, uses a plain text search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                },
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1-50). Default 10.",
                },
            },
            "required": ["account", "query"],
        },
    },
    {
        "name": "email_mark_read",
        "description": "Mark one or more emails as read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                },
                "email_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of email IDs to mark as read.",
                },
            },
            "required": ["account", "email_ids"],
        },
    },
    {
        "name": "email_send",
        "description": (
            "Send an email from one of Ky's accounts. IRREVERSIBLE — only call this "
            "after Ky has explicitly approved the final recipient, subject, and body, "
            "and set confirmed=true. "
            "Account routing: 'personal' (kydanjenkins04@gmail.com) for personal mail; "
            "'business_outlook' (kydan@kljsystems.com.au) is the default for business mail; "
            "'business_gmail' (kljsystems@gmail.com) only when Ky explicitly asks for it. "
            "If Ky has not specified which account, do NOT guess — ask him first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                    "description": "Which account to send from.",
                },
                "to":      {"type": "string", "description": "Recipient email address. Comma-separate multiple."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body":    {"type": "string", "description": "Email body. Plain text or HTML."},
                "cc":      {"type": "string", "description": "Optional CC addresses, comma-separated."},
                "bcc":     {"type": "string", "description": "Optional BCC addresses, comma-separated."},
                "html":    {"type": "boolean", "description": "True if body is HTML. Default false (plain text)."},
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true. Set ONLY after Ky has explicitly approved the final email content.",
                },
            },
            "required": ["account", "to", "subject", "body", "confirmed"],
        },
    },
    {
        "name": "email_label",
        "description": (
            "Add or remove labels/categories on one or more emails for organisation. "
            "Gmail: creates the label automatically if it doesn't exist. "
            "Outlook: applies as named categories. "
            "Use during triage to tag URGENT emails 'Priority', newsletters 'Newsletter', "
            "invoices 'Finance', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                },
                "email_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email IDs to label (from email_list or email_search).",
                },
                "add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label/category names to apply, e.g. ['Priority', 'KAOS'].",
                },
                "remove": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label/category names to remove.",
                },
            },
            "required": ["account", "email_ids"],
        },
    },
    {
        "name": "email_move",
        "description": (
            "Move one or more emails to a named folder. "
            "Gmail: creates the label/folder automatically if it doesn't exist, then archives from inbox. "
            "Outlook: creates the folder if it doesn't exist, then moves. "
            "Use 'Archive' to archive without a folder, 'Trash' to delete. "
            "Good folder names: 'Newsletters', 'Receipts', 'Finance', 'KAOS', 'Clients'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "enum": ["personal", "business_gmail", "business_outlook"],
                },
                "email_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email IDs to move.",
                },
                "folder": {
                    "type": "string",
                    "description": "Destination folder name. Use 'Archive' to archive, 'Trash' to delete.",
                },
            },
            "required": ["account", "email_ids", "folder"],
        },
    },
    {
        "name": "email_accounts",
        "description": "List the email accounts Tristan can send from, with their addresses and routing rules.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Gmail ─────────────────────────────────────────────────────────────────────

def _gmail_service(account: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_file = GMAIL_PERSONAL_TOKEN if account == "personal" else GMAIL_BUSINESS_TOKEN
    if not token_file or not os.path.exists(token_file):
        raise RuntimeError(
            f"Gmail token for '{account}' not found at {token_file or '(unset)'}. "
            "Run the Gmail OAuth bootstrap (see Tristan setup doc)."
        )
    creds = Credentials.from_authorized_user_file(token_file, GMAIL_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError(f"Gmail creds for '{account}' invalid and cannot refresh — re-run OAuth bootstrap.")
    return build("gmail", "v1", credentials=creds)


def _build_mime(sender: str, to: str, subject: str, body: str,
                cc: str = "", bcc: str = "", html: bool = False) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"]    = sender
    msg["To"]      = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg.attach(MIMEText(body, "html" if html else "plain", "utf-8"))
    return msg


def _send_gmail(account: str, sender: str, inputs: dict) -> str:
    service = _gmail_service(account)
    mime = _build_mime(
        sender,
        inputs["to"],
        inputs.get("subject", ""),
        inputs.get("body", ""),
        inputs.get("cc", ""),
        inputs.get("bcc", ""),
        bool(inputs.get("html", False)),
    )
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent from {sender} to {inputs['to']} (Gmail id: {sent.get('id', '?')})."


# ── Microsoft Graph (Outlook) ─────────────────────────────────────────────────

def _graph_token() -> str:
    """Client-credentials flow → app token with Mail.Send. Token cached to disk."""
    import json
    import time
    import requests

    if MS_GRAPH_TOKEN_FILE and os.path.exists(MS_GRAPH_TOKEN_FILE):
        try:
            with open(MS_GRAPH_TOKEN_FILE) as f:
                cached = json.load(f)
            if cached.get("expires_at", 0) > time.time() + 60:
                return cached["access_token"]
        except Exception:
            pass

    if not (MS_GRAPH_CLIENT_ID and MS_GRAPH_CLIENT_SECRET and MS_GRAPH_TENANT_ID):
        raise RuntimeError("Microsoft Graph credentials not configured — see Tristan setup doc.")

    url  = f"https://login.microsoftonline.com/{MS_GRAPH_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id":     MS_GRAPH_CLIENT_ID,
        "client_secret": MS_GRAPH_CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
        "grant_type":    "client_credentials",
    }
    resp = requests.post(url, data=data, timeout=20)
    resp.raise_for_status()
    tok = resp.json()
    access = tok["access_token"]
    if MS_GRAPH_TOKEN_FILE:
        try:
            with open(MS_GRAPH_TOKEN_FILE, "w") as f:
                json.dump({"access_token": access, "expires_at": time.time() + int(tok.get("expires_in", 3600))}, f)
        except Exception:
            pass
    return access


def _send_outlook(sender: str, inputs: dict) -> str:
    import requests

    token = _graph_token()

    def _recipients(addrs: str):
        return [{"emailAddress": {"address": a.strip()}} for a in addrs.split(",") if a.strip()]

    message = {
        "subject": inputs.get("subject", ""),
        "body": {
            "contentType": "HTML" if inputs.get("html") else "Text",
            "content":     inputs.get("body", ""),
        },
        "toRecipients": _recipients(inputs.get("to", "")),
    }
    if inputs.get("cc"):
        message["ccRecipients"]  = _recipients(inputs["cc"])
    if inputs.get("bcc"):
        message["bccRecipients"] = _recipients(inputs["bcc"])

    url  = f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message": message, "saveToSentItems": True},
        timeout=20,
    )
    if resp.status_code not in (200, 202):
        return f"Outlook send failed ({resp.status_code}): {resp.text}"
    return f"Email sent from {sender} to {inputs['to']} via Outlook/Graph."


# ── Contacts ─────────────────────────────────────────────────────────────────

def _gmail_contacts(token_path: str, query: str) -> list[dict]:
    """Search one Gmail account's contacts. Returns list of {name, emails, phones}."""
    if not token_path or not os.path.exists(token_path):
        return []
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        service = build("people", "v1", credentials=creds)
        result  = service.people().searchContacts(
            query=query,
            readMask="names,emailAddresses,phoneNumbers",
            pageSize=5,
        ).execute()
        contacts = []
        for c in result.get("results", []):
            p      = c.get("person", {})
            names  = p.get("names", [])
            name   = names[0].get("displayName", "") if names else ""
            emails = [e["value"] for e in p.get("emailAddresses", [])]
            phones = [ph["value"] for ph in p.get("phoneNumbers", [])]
            if name or emails:
                contacts.append({"name": name, "emails": emails, "phones": phones})
        return contacts
    except Exception:
        return []


def _outlook_contacts(query: str) -> list[dict]:
    """Search Outlook/Microsoft 365 contacts via Graph people endpoint."""
    try:
        import requests
        token = _graph_token()
        resp  = requests.get(
            f"https://graph.microsoft.com/v1.0/users/{OUTLOOK_SENDER}/people",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$search": query,
                "$select": "displayName,scoredEmailAddresses,phones",
                "$top": 5,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        contacts = []
        for p in resp.json().get("value", []):
            name   = p.get("displayName", "")
            emails = [e["address"] for e in p.get("scoredEmailAddresses", []) if e.get("address")]
            phones = [ph["number"] for ph in p.get("phones", []) if ph.get("number")]
            if name or emails:
                contacts.append({"name": name, "emails": emails, "phones": phones})
        return contacts
    except Exception:
        return []


def _contacts_search(query: str) -> str:
    """Search all three contact sources, merge, deduplicate by email."""
    results = []
    results += _gmail_contacts(GMAIL_PERSONAL_TOKEN,  query)
    results += _gmail_contacts(GMAIL_BUSINESS_TOKEN,  query)
    results += _outlook_contacts(query)

    # Deduplicate by first email address
    seen, merged = set(), []
    for c in results:
        key = c["emails"][0].lower() if c["emails"] else c["name"].lower()
        if key not in seen:
            seen.add(key)
            merged.append(c)

    if not merged:
        return f"No contacts found matching '{query}'."

    lines = []
    for c in merged:
        line = c["name"] or "(no name)"
        if c["emails"]:
            line += f" — {', '.join(c['emails'])}"
        if c["phones"]:
            line += f" · {c['phones'][0]}"
        lines.append(line)
    return "\n".join(lines)


# ── Gmail read helpers ────────────────────────────────────────────────────────

def _decode_gmail_body(payload: dict) -> str:
    """Extract plain-text body from a Gmail message payload, falling back to HTML stripped."""
    parts = payload.get("parts", [])
    if not parts:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return ""

    def _find(parts, mime):
        for p in parts:
            if p.get("mimeType") == mime:
                data = p.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if p.get("parts"):
                r = _find(p["parts"], mime)
                if r:
                    return r
        return ""

    text = _find(parts, "text/plain")
    if text:
        return text
    html_body = _find(parts, "text/html")
    if html_body:
        clean = re.sub(r"<[^>]+>", " ", html_body)
        return html.unescape(re.sub(r"\s+", " ", clean)).strip()
    return ""


def _gmail_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _gmail_list(account: str, folder: str, limit: int, unread_only: bool) -> str:
    svc = _gmail_service(account)
    folder_map = {"inbox": "INBOX", "sent": "SENT", "drafts": "DRAFT"}
    label = folder_map.get(folder, "INBOX")
    query = "is:unread" if unread_only else ""
    result = svc.users().messages().list(
        userId="me", labelIds=[label], q=query,
        maxResults=min(limit, 50),
    ).execute()
    msgs = result.get("messages", [])
    if not msgs:
        return "No emails found."
    lines = []
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                           metadataHeaders=["From", "Subject", "Date"]).execute()
        hdrs = full.get("payload", {}).get("headers", [])
        snippet = full.get("snippet", "")[:120]
        is_unread = "UNREAD" in full.get("labelIds", [])
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {_gmail_header(hdrs, 'From')}\n"
            f"  Subject: {_gmail_header(hdrs, 'Subject')}\n"
            f"  Date: {_gmail_header(hdrs, 'Date')}\n"
            f"  Read: {'No' if is_unread else 'Yes'}\n"
            f"  Preview: {snippet}"
        )
    return "\n\n".join(lines)


def _gmail_read(account: str, email_id: str, mark_read: bool) -> str:
    svc = _gmail_service(account)
    msg = svc.users().messages().get(userId="me", id=email_id, format="full").execute()
    hdrs = msg.get("payload", {}).get("headers", [])
    body = _decode_gmail_body(msg.get("payload", {}))
    if mark_read and "UNREAD" in msg.get("labelIds", []):
        svc.users().messages().modify(
            userId="me", id=email_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    return (
        f"From: {_gmail_header(hdrs, 'From')}\n"
        f"To: {_gmail_header(hdrs, 'To')}\n"
        f"Subject: {_gmail_header(hdrs, 'Subject')}\n"
        f"Date: {_gmail_header(hdrs, 'Date')}\n\n"
        f"{body.strip()}"
    )


def _gmail_search(account: str, query: str, limit: int) -> str:
    svc = _gmail_service(account)
    result = svc.users().messages().list(userId="me", q=query, maxResults=min(limit, 50)).execute()
    msgs = result.get("messages", [])
    if not msgs:
        return "No emails found."
    lines = []
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                           metadataHeaders=["From", "Subject", "Date"]).execute()
        hdrs = full.get("payload", {}).get("headers", [])
        snippet = full.get("snippet", "")[:120]
        is_unread = "UNREAD" in full.get("labelIds", [])
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {_gmail_header(hdrs, 'From')}\n"
            f"  Subject: {_gmail_header(hdrs, 'Subject')}\n"
            f"  Date: {_gmail_header(hdrs, 'Date')}\n"
            f"  Read: {'No' if is_unread else 'Yes'}\n"
            f"  Preview: {snippet}"
        )
    return "\n\n".join(lines)


def _gmail_mark_read(account: str, email_ids: list) -> str:
    svc = _gmail_service(account)
    for eid in email_ids:
        svc.users().messages().modify(
            userId="me", id=eid,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    return f"Marked {len(email_ids)} email(s) as read."


# ── Outlook read helpers ───────────────────────────────────────────────────────

def _graph_get(path: str, params: dict = None) -> dict:
    import requests
    token = _graph_token()
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def _graph_patch(path: str, body: dict) -> None:
    import requests
    token = _graph_token()
    resp = requests.patch(
        f"https://graph.microsoft.com/v1.0{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=20,
    )
    resp.raise_for_status()


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", clean)).strip()


def _outlook_list(sender: str, folder: str, limit: int, unread_only: bool) -> str:
    folder_map = {"inbox": "inbox", "sent": "sentitems", "drafts": "drafts"}
    f = folder_map.get(folder, "inbox")
    params = {
        "$top": min(limit, 50),
        "$orderby": "receivedDateTime desc",
        "$select": "id,from,subject,receivedDateTime,bodyPreview,isRead",
    }
    if unread_only:
        params["$filter"] = "isRead eq false"
    data = _graph_get(f"/users/{sender}/mailFolders/{f}/messages", params)
    msgs = data.get("value", [])
    if not msgs:
        return "No emails found."
    lines = []
    for m in msgs:
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {m.get('from', {}).get('emailAddress', {}).get('address', '?')}\n"
            f"  Subject: {m.get('subject', '')}\n"
            f"  Date: {m.get('receivedDateTime', '')}\n"
            f"  Read: {'Yes' if m.get('isRead') else 'No'}\n"
            f"  Preview: {m.get('bodyPreview', '')[:120]}"
        )
    return "\n\n".join(lines)


def _outlook_read(sender: str, email_id: str, mark_read: bool) -> str:
    data = _graph_get(f"/users/{sender}/messages/{email_id}", {"$select": "from,toRecipients,subject,receivedDateTime,body"})
    body_content = data.get("body", {}).get("content", "")
    if data.get("body", {}).get("contentType", "").lower() == "html":
        body_content = _strip_html(body_content)
    if mark_read:
        _graph_patch(f"/users/{sender}/messages/{email_id}", {"isRead": True})
    to_addrs = ", ".join(
        r.get("emailAddress", {}).get("address", "")
        for r in data.get("toRecipients", [])
    )
    return (
        f"From: {data.get('from', {}).get('emailAddress', {}).get('address', '?')}\n"
        f"To: {to_addrs}\n"
        f"Subject: {data.get('subject', '')}\n"
        f"Date: {data.get('receivedDateTime', '')}\n\n"
        f"{body_content.strip()}"
    )


def _outlook_search(sender: str, query: str, limit: int) -> str:
    params = {
        "$search": f'"{query}"',
        "$top": min(limit, 50),
        "$select": "id,from,subject,receivedDateTime,bodyPreview,isRead",
    }
    data = _graph_get(f"/users/{sender}/messages", params)
    msgs = data.get("value", [])
    if not msgs:
        return "No emails found."
    lines = []
    for m in msgs:
        lines.append(
            f"ID: {m['id']}\n"
            f"  From: {m.get('from', {}).get('emailAddress', {}).get('address', '?')}\n"
            f"  Subject: {m.get('subject', '')}\n"
            f"  Date: {m.get('receivedDateTime', '')}\n"
            f"  Read: {'Yes' if m.get('isRead') else 'No'}\n"
            f"  Preview: {m.get('bodyPreview', '')[:120]}"
        )
    return "\n\n".join(lines)


def _outlook_mark_read(sender: str, email_ids: list) -> str:
    for eid in email_ids:
        _graph_patch(f"/users/{sender}/messages/{eid}", {"isRead": True})
    return f"Marked {len(email_ids)} email(s) as read."


# ── Label / Move — Gmail ───────────────────────────────────────────────────────

def _gmail_get_or_create_label(svc, label_name: str) -> str:
    """Return label ID, creating it if it doesn't exist."""
    result = svc.users().labels().list(userId="me").execute()
    for lbl in result.get("labels", []):
        if lbl["name"].lower() == label_name.lower():
            return lbl["id"]
    created = svc.users().labels().create(
        userId="me",
        body={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def _gmail_label(account: str, email_ids: list, add: list, remove: list) -> str:
    svc = _gmail_service(account)
    all_labels = {l["name"].lower(): l["id"] for l in svc.users().labels().list(userId="me").execute().get("labels", [])}
    add_ids    = [_gmail_get_or_create_label(svc, l) for l in add]
    remove_ids = [all_labels[l.lower()] for l in remove if l.lower() in all_labels]
    for eid in email_ids:
        svc.users().messages().modify(
            userId="me", id=eid,
            body={"addLabelIds": add_ids, "removeLabelIds": remove_ids},
        ).execute()
    return f"Applied labels {add} to {len(email_ids)} email(s)." + (f" Removed {remove}." if remove else "")


def _gmail_move(account: str, email_ids: list, folder: str) -> str:
    svc = _gmail_service(account)
    fl  = folder.lower()
    if fl in ("archive",):
        for eid in email_ids:
            svc.users().messages().modify(userId="me", id=eid, body={"removeLabelIds": ["INBOX"]}).execute()
        return f"Archived {len(email_ids)} email(s)."
    if fl in ("trash", "bin", "delete"):
        for eid in email_ids:
            svc.users().messages().trash(userId="me", id=eid).execute()
        return f"Trashed {len(email_ids)} email(s)."
    if fl == "inbox":
        for eid in email_ids:
            svc.users().messages().modify(userId="me", id=eid, body={"addLabelIds": ["INBOX"]}).execute()
        return f"Moved {len(email_ids)} email(s) back to inbox."
    # User folder — create label and archive from inbox
    label_id = _gmail_get_or_create_label(svc, folder)
    for eid in email_ids:
        svc.users().messages().modify(
            userId="me", id=eid,
            body={"addLabelIds": [label_id], "removeLabelIds": ["INBOX"]},
        ).execute()
    return f"Moved {len(email_ids)} email(s) to '{folder}'."


# ── Label / Move — Outlook ────────────────────────────────────────────────────

def _graph_post(path: str, body: dict) -> dict:
    import requests
    token = _graph_token()
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=20,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _outlook_get_or_create_folder(sender: str, folder_name: str) -> str:
    """Return folder ID (well-known name or by display name), creating if needed."""
    well_known = {
        "inbox": "inbox", "sent": "sentitems", "drafts": "drafts",
        "archive": "archive", "trash": "deleteditems", "bin": "deleteditems",
        "delete": "deleteditems", "junk": "junkemail",
    }
    if folder_name.lower() in well_known:
        return well_known[folder_name.lower()]
    data = _graph_get(f"/users/{sender}/mailFolders", {"$filter": f"displayName eq '{folder_name}'", "$top": 1})
    folders = data.get("value", [])
    if folders:
        return folders[0]["id"]
    result = _graph_post(f"/users/{sender}/mailFolders", {"displayName": folder_name})
    return result["id"]


def _outlook_label(sender: str, email_ids: list, add: list, remove: list) -> str:
    for eid in email_ids:
        data    = _graph_get(f"/users/{sender}/messages/{eid}", {"$select": "categories"})
        current = set(data.get("categories", []))
        current.update(add)
        for rl in remove:
            current.discard(rl)
        _graph_patch(f"/users/{sender}/messages/{eid}", {"categories": list(current)})
    return f"Applied categories {add} to {len(email_ids)} email(s)." + (f" Removed {remove}." if remove else "")


def _outlook_move(sender: str, email_ids: list, folder: str) -> str:
    folder_id = _outlook_get_or_create_folder(sender, folder)
    moved = 0
    for eid in email_ids:
        try:
            _graph_post(f"/users/{sender}/messages/{eid}/move", {"destinationId": folder_id})
            moved += 1
        except Exception:
            pass
    return f"Moved {moved}/{len(email_ids)} email(s) to '{folder}'."


# ── Handler ───────────────────────────────────────────────────────────────────

def handle(name: str, inputs: dict) -> str:
    if name == "email_accounts":
        lines = ["Tristan's accounts:"]
        for key, (provider, addr) in _ACCOUNTS.items():
            lines.append(f"  - {key}: {addr} ({provider})")
        lines.append("")
        lines.append("Routing: personal mail → personal; business mail → business_outlook (default); "
                     "business_gmail only on explicit request.")
        return "\n".join(lines)

    if name == "contacts_search":
        try:
            return _contacts_search(inputs.get("query", ""))
        except Exception as e:
            return f"contacts_search error: {e}"

    if name == "email_list":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        folder = inputs.get("folder", "inbox")
        limit = int(inputs.get("limit", 20))
        unread_only = bool(inputs.get("unread_only", False))
        try:
            if provider == "gmail":
                return _gmail_list(account, folder, limit, unread_only)
            return _outlook_list(addr, folder, limit, unread_only)
        except Exception as e:
            return f"email_list error ({account}): {e}"

    if name == "email_read":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        email_id = inputs.get("email_id", "")
        mark_read = bool(inputs.get("mark_read", False))
        try:
            if provider == "gmail":
                return _gmail_read(account, email_id, mark_read)
            return _outlook_read(addr, email_id, mark_read)
        except Exception as e:
            return f"email_read error ({account}): {e}"

    if name == "email_search":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        query = inputs.get("query", "")
        limit = int(inputs.get("limit", 10))
        try:
            if provider == "gmail":
                return _gmail_search(account, query, limit)
            return _outlook_search(addr, query, limit)
        except Exception as e:
            return f"email_search error ({account}): {e}"

    if name == "email_mark_read":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        email_ids = inputs.get("email_ids", [])
        try:
            if provider == "gmail":
                return _gmail_mark_read(account, email_ids)
            return _outlook_mark_read(addr, email_ids)
        except Exception as e:
            return f"email_mark_read error ({account}): {e}"

    if name == "email_label":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        email_ids = inputs.get("email_ids", [])
        add    = inputs.get("add", [])
        remove = inputs.get("remove", [])
        if not email_ids:
            return "No email IDs provided."
        try:
            if provider == "gmail":
                return _gmail_label(account, email_ids, add, remove)
            return _outlook_label(addr, email_ids, add, remove)
        except Exception as e:
            return f"email_label error ({account}): {e}"

    if name == "email_move":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'."
        provider, addr = _ACCOUNTS[account]
        email_ids = inputs.get("email_ids", [])
        folder    = inputs.get("folder", "").strip()
        if not email_ids:
            return "No email IDs provided."
        if not folder:
            return "No destination folder specified."
        try:
            if provider == "gmail":
                return _gmail_move(account, email_ids, folder)
            return _outlook_move(addr, email_ids, folder)
        except Exception as e:
            return f"email_move error ({account}): {e}"

    if name == "email_send":
        account = inputs.get("account", "")
        if account not in _ACCOUNTS:
            return f"Unknown account '{account}'. Valid: {', '.join(_ACCOUNTS)}."

        if not inputs.get("confirmed"):
            return (
                "BLOCKED: confirmed is not true. Sending is irreversible — do not send until Ky has "
                "explicitly approved the final recipient, subject, and body. Confirm with him, then retry "
                "with confirmed=true."
            )
        if not inputs.get("to", "").strip():
            return "No recipient provided."

        provider, sender = _ACCOUNTS[account]
        try:
            if provider == "gmail":
                return _send_gmail(account, sender, inputs)
            return _send_outlook(sender, inputs)
        except Exception as e:
            return f"Email send error ({account}): {e}"

    return f"Unknown email tool: {name}"
