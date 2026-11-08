"""Verify Google id_tokens server-side."""
import os
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
def verify_google_id_token(raw_token):
    if not GOOGLE_CLIENT_ID: raise ValueError("GOOGLE_CLIENT_ID not configured")
    try:
        info = google_id_token.verify_oauth2_token(raw_token, google_requests.Request(), audience=GOOGLE_CLIENT_ID)
    except Exception as exc: raise ValueError(f"token verification failed: {exc}") from exc
    if not info.get("email_verified"): raise ValueError("email not verified")
    return info
