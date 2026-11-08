"""Security hardening."""
import pathlib
ROOT = pathlib.Path(".")

# 1. login.html demo creds
p = ROOT / "frontend/login.html"
if p.exists():
    s = p.read_text(encoding="utf-8")
    s = s.replace(
        '<div class="text-[11px] text-slate-500 border-t border-slate-800 pt-3 space-y-1">',
        '<div id="demo-creds" class="text-[11px] text-slate-500 border-t border-slate-800 pt-3 space-y-1">')
    hook = '  if (!/^(localhost|127\\.0\\.0\\.1)$/.test(location.hostname)) { var dc = document.getElementById("demo-creds"); if (dc) dc.style.display = "none"; }\n'
    m = "  window.handleGoogleLogin = async (response) => {"
    if m in s and "demo-creds\").style" not in s:
        s = s.replace(m, hook + m, 1)
    p.write_text(s, encoding="utf-8")
    print("OK login.html: demo creds gated")

# 2. google.py
g = ROOT / "backend/app/auth/google.py"
g.parent.mkdir(parents=True, exist_ok=True)
g.write_text('''"""Verify Google id_tokens server-side."""
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
''', encoding="utf-8")
print("OK backend/app/auth/google.py created")

req = ROOT / "backend/requirements.txt"
if req.exists() and "google-auth" not in req.read_text(encoding="utf-8"):
    with req.open("a") as fh: fh.write("\ngoogle-auth>=2.30.0\n")
    print("OK google-auth added")

print("Done.")
