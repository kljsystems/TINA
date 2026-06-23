"""TINA Tool — Google Drive: search, list, and read files (read-only)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CREDENTIALS_FILE, DRIVE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

DEFINITIONS = [
    {
        "name": "gdrive_search",
        "description": (
            "Search for files in Google Drive by name or content. "
            "Returns file names, IDs, types, and last modified dates. "
            "Use to find documents, spreadsheets, or any file Ky has in Drive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — file name, keyword, or topic to find.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Defaults to 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "gdrive_read",
        "description": (
            "Read the text content of a Google Drive file by its ID. "
            "Works for Google Docs (exports as plain text), Sheets (exports as CSV), "
            "and plain text/PDF files. Get the file ID from gdrive_search or gdrive_list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "The Google Drive file ID.",
                },
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "gdrive_list",
        "description": (
            "List files in a Google Drive folder, sorted by most recently modified. "
            "Omit folder_id to browse the top level of Drive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "description": "ID of the folder to list. Omit for the root Drive.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max files to return. Defaults to 20.",
                },
            },
            "required": [],
        },
    },
]


def _service():
    import warnings; warnings.filterwarnings("ignore")
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API libraries not installed. Ask Sam to run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"

    creds = None
    if os.path.exists(DRIVE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(DRIVE_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                return None, "credentials.json not found — Google OAuth not configured."
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(DRIVE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds), None


def handle(name: str, inputs: dict) -> str:
    service, err = _service()
    if err:
        return err
    if service is None:
        return "Google Drive not configured."

    if name == "gdrive_search":
        query = inputs.get("query", "")
        limit = int(inputs.get("limit", 10))
        try:
            safe_q = query.replace("'", "\\'")
            q = f"(name contains '{safe_q}' or fullText contains '{safe_q}') and trashed = false"
            results = service.files().list(
                q=q,
                pageSize=limit,
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc",
            ).execute()
            files = results.get("files", [])
            if not files:
                return f"No files found matching '{query}'"
            lines = [f"GOOGLE DRIVE SEARCH — '{query}' ({len(files)} results)\n"]
            for f in files:
                mime = f.get("mimeType", "").replace("application/vnd.google-apps.", "").replace("application/", "")
                modified = f.get("modifiedTime", "")[:10]
                lines.append(f"  [{mime}] {f['name']}")
                lines.append(f"  ID: {f['id']}  Modified: {modified}")
            return "\n".join(lines)
        except Exception as e:
            return f"Drive search failed: {e}"

    if name == "gdrive_read":
        file_id = inputs.get("file_id", "")
        if not file_id:
            return "file_id is required"
        try:
            meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
            mime = meta.get("mimeType", "")
            fname = meta.get("name", file_id)

            if mime == "application/vnd.google-apps.document":
                content = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            elif mime == "application/vnd.google-apps.spreadsheet":
                content = service.files().export(fileId=file_id, mimeType="text/csv").execute()
            elif mime.startswith("application/vnd.google-apps."):
                return f"Cannot read {mime.split('.')[-1]} files — only Docs and Sheets are supported."
            else:
                content = service.files().get_media(fileId=file_id).execute()

            text = content.decode("utf-8") if isinstance(content, bytes) else str(content)
            truncated = len(text) > 8000
            return (
                f"FILE: {fname}\n{'=' * 60}\n"
                + text[:8000]
                + ("\n\n[truncated — file is larger than 8000 chars]" if truncated else "")
            )
        except Exception as e:
            return f"Drive read failed: {e}"

    if name == "gdrive_list":
        folder_id = inputs.get("folder_id") or "root"
        limit = int(inputs.get("limit", 20))
        try:
            q = f"'{folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=q,
                pageSize=limit,
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc",
            ).execute()
            files = results.get("files", [])
            if not files:
                return f"No files found in folder '{folder_id}'"
            lines = [f"GOOGLE DRIVE — {len(files)} files\n"]
            for f in files:
                mime = f.get("mimeType", "")
                is_folder = mime == "application/vnd.google-apps.folder"
                label = "[DIR]" if is_folder else f"[{mime.replace('application/vnd.google-apps.', '').replace('application/', '')[:12]}]"
                modified = f.get("modifiedTime", "")[:10]
                lines.append(f"  {label} {f['name']}")
                lines.append(f"  ID: {f['id']}  Modified: {modified}")
            return "\n".join(lines)
        except Exception as e:
            return f"Drive list failed: {e}"

    return f"Unknown tool: {name}"
