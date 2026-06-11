"""
Run this once per Gmail account to authorise Tristan's send permission.

Usage:
    python scripts/auth_gmail.py personal
    python scripts/auth_gmail.py business

Saves tokens to:
    data/gmail_personal_token.json
    data/gmail_business_token.json
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

TOKEN_MAP = {
    "personal": ("data/gmail_personal_token.json",  "kydanjenkins04@gmail.com"),
    "business": ("data/gmail_business_token.json",  "kljsystems@gmail.com"),
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TOKEN_MAP:
        print("Usage: python scripts/auth_gmail.py personal|business")
        sys.exit(1)

    account            = sys.argv[1]
    token_path, email  = TOKEN_MAP[account]
    creds_file         = "credentials.json"

    if not os.path.exists(creds_file):
        print(f"credentials.json not found in {os.getcwd()}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        sys.exit(1)

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs("data", exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    print(f"Auth successful for {email}")
    print(f"Token saved to {token_path}")

    # Quick smoke test
    from googleapiclient.discovery import build
    svc  = build("gmail", "v1", credentials=creds)
    prof = svc.users().getProfile(userId="me").execute()
    print(f"Verified — logged in as {prof.get('emailAddress')}")

if __name__ == "__main__":
    main()
