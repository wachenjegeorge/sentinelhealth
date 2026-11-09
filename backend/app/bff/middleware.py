"""BFF shield: public path allowlist + auth + idempotency."""
from __future__ import annotations

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.security import verify_token

# Exact paths that do not require an Authorization header
PUBLIC_PATHS = {
    "/health", "/", "/login", "/register", "/worker", "/admin",
    "/admin/users", "/admin/verify", "/admin/incidents", "/admin/facilities", "/dept-head",
    "/profile", "/compliance", "/keph", "/sw.js",
    "/docs", "/openapi.json", "/favicon.ico",
}

# API endpoints that do not require an Authorization header (login, signup)
PUBLIC_ENDPOINTS = {
    "/api/bff/auth/login",
    "/api/bff/auth/register",
    "/api/bff/auth/register/worker",
    "/api/bff/auth/register/county-officer",
}

# Prefixes that should bypass auth (static assets, public APIs, and HTML sub-pages)
PUBLIC_PREFIXES = (
    "/api/bff/facilities",
    "/static/",
    "/admin/intel",  # <--- ADDED: Allows the browser to load the HTML shell for the deep-dive page
)


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        path = request.url.path

        is_public = (
            path in PUBLIC_PATHS
            or path in PUBLIC_ENDPOINTS
            or path.startswith(PUBLIC_PREFIXES)
        )
        
        if is_public:
            r = await call_next(request)
            r.headers["x-request-id"] = rid
            return r

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "missing bearer token"}, status_code=401)
        try:
            claims = verify_token(auth[7:])
        except ValueError:
            return JSONResponse({"detail": "invalid token"}, status_code=401)

        request.state.claims = claims
        request.state.request_id = rid

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not request.headers.get("idempotency-key"):
                return JSONResponse({"detail": "idempotency-key header required"}, status_code=400)

        r = await call_next(request)
        r.headers["x-request-id"] = rid
        return r
