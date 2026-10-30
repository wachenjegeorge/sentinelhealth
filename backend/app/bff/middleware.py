"""The BFF shield: tenant extraction, idempotency-key enforcement.

PUBLIC paths skip auth entirely:
  - /health, /, /docs, /openapi.json   (liveness + docs)
  - /api/bff/worker/login              (issues the token; cannot require one)

Every other path requires `Authorization: Bearer <jwt>`.
Every mutation additionally requires `Idempotency-Key`.
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.db import tenant_ctx
from app.security import verify_token

PUBLIC_PATHS = {"/health", "/", "/docs", "/openapi.json"}
PUBLIC_PREFIXES = ("/api/bff/worker/login",)


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
            return JSONResponse(
                {"detail": "missing bearer token"}, status_code=401
            )
        try:
            claims = verify_token(auth[7:])
        except ValueError:
            return JSONResponse(
                {"detail": "invalid token"}, status_code=401
            )

        token = tenant_ctx.set(claims["facility_id"])
        request.state.claims = claims
        request.state.request_id = rid

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not request.headers.get("idempotency-key"):
                tenant_ctx.reset(token)
                return JSONResponse(
                    {"detail": "idempotency-key header required"},
                    status_code=400,
                )

        try:
            r = await call_next(request)
        finally:
            tenant_ctx.reset(token)

        r.headers["x-request-id"] = rid
        return r
