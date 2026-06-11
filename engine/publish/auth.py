"""
OAuth 2.0 for the YouTube Data API v3.

First run opens a browser for consent; the token is cached to `token.json` so
every later run is non-interactive (auto-refreshes). Requires a Desktop-app
OAuth client downloaded to `client_secrets.json` in the project root.
See docs/adr/0002-youtube-oauth.md.
"""
from __future__ import annotations
import os

# Scopes match the OAuth consent screen setup (image-3 step 4).
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CLIENT_SECRETS = os.path.join(_ROOT, "client_secrets.json")
TOKEN_FILE = os.path.join(_ROOT, "token.json")


def get_credentials():
    """Return valid YouTube OAuth credentials, refreshing or prompting as needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS):
                raise FileNotFoundError(
                    f"Missing {CLIENT_SECRETS}. In Google Cloud: enable YouTube "
                    "Data API v3, create an OAuth 'Desktop app' client, download "
                    "the JSON here. See docs/adr/0002-youtube-oauth.md."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)  # one-time browser consent
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def get_service():
    """Return an authenticated YouTube Data API v3 client."""
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=get_credentials())


if __name__ == "__main__":
    # One-time setup: run this in a terminal with a browser to complete OAuth
    # consent (caches token.json), then confirm which channel we're authed as.
    #   python3 -m engine.publish.auth
    yt = get_service()
    me = yt.channels().list(part="snippet,statistics", mine=True).execute()
    if me.get("items"):
        ch = me["items"][0]
        print(f"✓ Authenticated as: {ch['snippet']['title']}")
        print(f"  subscribers: {ch['statistics'].get('subscriberCount', '?')}, "
              f"videos: {ch['statistics'].get('videoCount', '?')}")
        print("  token cached → token.json (later runs are non-interactive)")
    else:
        print("Authenticated, but no channel found on this account.")
