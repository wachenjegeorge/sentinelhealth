"""BFF shield: tenant + role extraction, idempotency-key enforcement."""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security import verify_token

PUBLIC_PATHS = {"/health", "/", "/login", "/worker", "/admin", "/sw.js",
                "/docs", "/openapi.json", "/favicon.ico"}
PUBLIC_PREFIXES = ("/api/bff/auth/", "/api/bff/facilities", "/static/")


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        path = request.url.path

        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
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
                return JSONResponse({"detail": "idempotency-key header required"},
                                    status_code=400)

        r = await call_next(request)
        r.headers["x-request-id"] = rid
        return r
