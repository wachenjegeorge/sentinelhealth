"""SentinelHealth production entrypoint.

Combines the BFF routers and monolith modules into one FastAPI app.
Works in both:
  - local:   backend/app/combined.py -> repo_root/frontend/
  - docker:  /app/app/combined.py    -> /app/frontend/
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.bff.middleware import TenantMiddleware

# ── API Routers ──────────────────────────────────────────
from app.bff.routes_admin import router as admin_router
from app.bff.routes_admin_approvals import router as approvals_router
from app.bff.routes_admin_verify import router as verify_router
from app.bff.routes_assistant import router as assistant_router
from app.bff.routes_auth import router as auth_router
from app.bff.routes_coach import router as coach_router
from app.bff.routes_department_head import router as dept_head_router
from app.bff.routes_hospital_depts import router as hospital_depts_router
from app.bff.routes_facilities import router as facilities_router
from app.bff.routes_impact import router as impact_router
from app.bff.routes_incidents import router as incidents_router
from app.bff.routes_intel import router as intel_router
from app.bff.routes_roster import router as roster_router
from app.bff.routes_shift_requests import router as shift_req_router
from app.bff.routes_simulator import router as simulator_router
from app.bff.routes_sync import router as sync_router
from app.bff.routes_telemetry import router as telemetry_router
from app.bff.routes_users import router as users_router
from app.bff.routes_wearable import router as wearable_router
from app.bff.routes_worker import router as worker_router

# ── Robust frontend path resolution ──────────────────────
# In docker:   /app/app/combined.py -> /app/frontend      (2 levels up)
# In local:    backend/app/combined.py -> <root>/frontend (3 levels up)
_here = Path(__file__).resolve()
_candidates = [
    _here.parent.parent / "frontend",         # docker layout
    _here.parent.parent.parent / "frontend",  # local layout
]
FRONTEND_DIR = next((p for p in _candidates if p.exists()), _candidates[0])

app = FastAPI(
    title="SentinelHealth Kenya",
    description="Workforce health early warning for Kenyan healthcare providers",
    version="0.5.0",
)

app.add_middleware(TenantMiddleware)

# ── Register API routers ─────────────────────────────────
app.include_router(auth_router)
app.include_router(facilities_router)
app.include_router(sync_router)
app.include_router(worker_router)
app.include_router(admin_router)
app.include_router(approvals_router)
app.include_router(verify_router)
app.include_router(users_router)
app.include_router(incidents_router)
app.include_router(impact_router)
app.include_router(assistant_router)
app.include_router(roster_router)
app.include_router(simulator_router)
app.include_router(coach_router)
app.include_router(dept_head_router)
app.include_router(hospital_depts_router)
app.include_router(wearable_router)
app.include_router(shift_req_router)
app.include_router(telemetry_router)
app.include_router(intel_router)


# ── Health ───────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "sentinelhealth", "version": "0.5.0"}


# ── HTML pages ───────────────────────────────────────────
@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/register", include_in_schema=False)
def register_page():
    return FileResponse(FRONTEND_DIR / "register.html")


@app.get("/worker", include_in_schema=False)
def worker_page():
    return FileResponse(FRONTEND_DIR / "worker.html")


@app.get("/profile", include_in_schema=False)
def profile_page():
    return FileResponse(FRONTEND_DIR / "profile.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(FRONTEND_DIR / "admin.html")


@app.get("/admin/users", include_in_schema=False)
def admin_users_page():
    return FileResponse(FRONTEND_DIR / "admin-users.html")


@app.get("/admin/incidents", include_in_schema=False)
def admin_incidents_page():
    return FileResponse(FRONTEND_DIR / "admin-incidents.html")


@app.get("/admin/verify", include_in_schema=False)
def admin_verify_page():
    return FileResponse(FRONTEND_DIR / "admin-verify.html")


@app.get("/dept-head", include_in_schema=False)
def dept_head_page():
    return FileResponse(FRONTEND_DIR / "admin-dept-head.html")


@app.get("/admin/facilities", include_in_schema=False)
def admin_facilities_page():
    return FileResponse(FRONTEND_DIR / "admin-facilities.html")


@app.get("/admin/intel/{county}", include_in_schema=False)
def admin_intel_page(county: str):
    return FileResponse(FRONTEND_DIR / "admin-intel.html")


@app.get("/compliance", include_in_schema=False)
def compliance_page():
    return FileResponse(FRONTEND_DIR / "compliance.html")


@app.get("/keph", include_in_schema=False)
def keph_page():
    return FileResponse(FRONTEND_DIR / "keph.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


# ── Static assets ────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
