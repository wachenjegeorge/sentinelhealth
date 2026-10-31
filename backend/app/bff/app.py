"""BFF FastAPI app: public entry + PWA frontend."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.bff.middleware import TenantMiddleware
from app.bff.routes_admin import router as admin_router
from app.bff.routes_assistant import router as assistant_router
from app.bff.routes_auth import router as auth_router
from app.bff.routes_facilities import router as facilities_router
from app.bff.routes_sync import router as sync_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="SentinelHealth BFF", version="0.3.0")
app.add_middleware(TenantMiddleware)

app.include_router(auth_router)
app.include_router(facilities_router)
app.include_router(sync_router)
app.include_router(admin_router)
app.include_router(assistant_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "bff"}


@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/worker", include_in_schema=False)
def worker_page():
    return FileResponse(FRONTEND_DIR / "worker.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(FRONTEND_DIR / "admin.html")


# PWA: serve at root scope so the SW can control all pages
@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
