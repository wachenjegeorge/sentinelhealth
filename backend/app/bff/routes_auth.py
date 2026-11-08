"""Auth routes — 4-role registration with hierarchical verification and Google OAuth."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
import os
import traceback

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.audit import append_audit
from app.db import AdminSession, with_tenant
from app.modules.auth import service as auth
from app.modules.auth.role_rules import role_allowed_for_level, department_allowed_for_level
from app.security import issue_token

router = APIRouter(prefix="/api/bff/auth", tags=["auth"])

# ── Login rate limiting (in-memory, single worker) ─────────────
from collections import defaultdict
import time as _time

_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 5


def _check_login_rate(request: Request, username: str) -> None:
    key = f"{(request.client.host if request.client else 'unknown')}:{username}"
    now = _time.time()
    _login_attempts[key] = [t for t in _login_attempts[key] if now - t < _RATE_WINDOW]
    if len(_login_attempts[key]) >= _RATE_MAX:
        raise HTTPException(429, "Too many login attempts. Try again in 60 seconds.")
    _login_attempts[key].append(now)




# ── Request/Response Models ─────────────────────────────────────

class LoginPayload(BaseModel):
    username: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class CountyOfficerReg(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    county: str = Field(min_length=2, max_length=40)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)


class HospitalHeadReg(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    occupation: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    facility_id: str


class WorkerReg(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    occupation: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    primary_department: str = Field(min_length=2, max_length=60)
    facility_id: str | None = None




class DepartmentHeadReg(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    occupation: str = Field(default="Department Head", max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    department: str = Field(min_length=2, max_length=60)




@router.post("/register/department-head")
async def register_department_head(payload: DepartmentHeadReg, request: Request):
    claims = request.state.claims
    if claims["role"] != "hospital_head":
        raise HTTPException(403, "hospital_head role required")

    async with AdminSession() as session:
        async with session.begin():
            try:
                uid = await auth.register_worker(
                    session, username=payload.username, password=payload.password,
                    full_name=payload.full_name, occupation=payload.occupation,
                    phone=payload.phone, facility_id=claims["facility_id"],
                    primary_department=payload.department,
                    created_by=claims["sub"])
            except ValueError as e:
                raise HTTPException(409, str(e))
            # Promote the new user to department_head role
            await session.execute(text(
                "UPDATE users SET role = 'department_head' WHERE id = :id"
            ), {"id": uid})
    return {"ok": True, "status": "pending_head_verification", "user_id": uid}


class VerifyPayload(BaseModel):
    approve: bool
    notes: str | None = None


class ChangePasswordPayload(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountPayload(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class GoogleAuthPayload(BaseModel):
    credential: str


# ── Login ────────────────────────────────────────────────────────
@router.post("/login")
async def login(payload: LoginPayload, request: Request):
    _check_login_rate(request, payload.username)
    async with AdminSession() as session:
        async with session.begin():
            result = await auth.authenticate(session, payload.username, payload.password)
            if result is None:
                raise HTTPException(401, "invalid credentials or account not yet verified")
            must_change = (await session.execute(text(
                "SELECT must_change_password FROM users WHERE id = :id"),
                {"id": result.user_id})).scalar()

    token = issue_token(user_id=result.user_id, username=result.username,
                        role=result.role, facility_id=result.facility_id,
                        county=result.county)
    return {
        "access_token": token, "token_type": "bearer",
        "role": result.role, "facility_id": result.facility_id,
        "county": result.county, "must_change_password": bool(must_change),
    }


# ── Google OAuth ─────────────────────────────────────────────────
@router.post("/google")
async def google_auth(payload: GoogleAuthPayload):
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")

    try:
        idinfo = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            client_id,
        )
    except Exception as e:
        print("TOKEN VERIFICATION FAILED:", type(e).__name__, str(e))
        traceback.print_exc()
        raise HTTPException(401, f"Invalid Google token: {str(e)[:100]}")

    google_sub = idinfo.get("sub", "")
    email = idinfo.get("email", "")

    if not email:
        raise HTTPException(400, "Google account has no email")

    async with AdminSession() as session:
        async with session.begin():
            user_row = (await session.execute(text("""
                SELECT id, username, role, facility_id, verification_status, active
                FROM users WHERE email = :e OR google_sub = :g LIMIT 1
            """), {"e": email, "g": google_sub})).mappings().first()

            if user_row is None:
                raise HTTPException(401,
                    f"No SentinelHealth account is linked to {email}. "
                    f"Register first, or ask an admin to link your email.")

            if not user_row["active"]:
                raise HTTPException(403, "Account is inactive")
            if user_row["verification_status"] != "verified":
                raise HTTPException(403, f"Account status: {user_row['verification_status']}")

            await session.execute(text(
                "UPDATE users SET google_sub = :g WHERE id = :id AND (google_sub IS NULL OR google_sub = '')"
            ), {"g": google_sub, "id": user_row["id"]})

    county = None
    async with AdminSession() as session:
        county = (await session.execute(text(
            "SELECT county FROM facilities WHERE id = :id"
        ), {"id": user_row["facility_id"]})).scalar()

    token = issue_token(
        user_id=user_row["id"], username=user_row["username"],
        role=user_row["role"], facility_id=user_row["facility_id"],
        county=county
    )
    return {
        "access_token": token, "token_type": "bearer",
        "role": user_row["role"], "facility_id": user_row["facility_id"],
        "county": county,
    }


# ── Registration Endpoints ───────────────────────────────────────
@router.post("/register/county-officer")
async def register_county_officer(payload: CountyOfficerReg):
    async with AdminSession() as session:
        async with session.begin():
            try:
                uid = await auth.register_county_officer(
                    session, username=payload.username, password=payload.password,
                    full_name=payload.full_name, county=payload.county,
                    email=payload.email, phone=payload.phone)
            except ValueError as e:
                raise HTTPException(409, str(e))
    return {"ok": True, "status": "pending_admin_verification", "user_id": uid}


@router.post("/register/hospital-head")
async def register_hospital_head(payload: HospitalHeadReg, request: Request):
    claims = request.state.claims
    if claims["role"] not in ("county_officer", "county_officer"):
        raise HTTPException(403, "county_officer role required")

    async with AdminSession() as session:
        async with session.begin():
            county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            target_county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": payload.facility_id})).scalar()
            if not target_county or target_county != county:
                raise HTTPException(403, "facility is outside your county")
            try:
                uid = await auth.register_hospital_head(
                    session, username=payload.username, password=payload.password,
                    full_name=payload.full_name, occupation=payload.occupation,
                    phone=payload.phone, facility_id=payload.facility_id,
                    created_by=claims["sub"])
            except ValueError as e:
                raise HTTPException(409, str(e))
    return {"ok": True, "status": "pending_officer_verification", "user_id": uid}


@router.post("/register/worker")
async def register_worker(payload: WorkerReg, request: Request):
    """Self-registration OR hospital_head/dept_head-invited.

    - Self-register: no auth, facility_id in payload, ends in pending dept_head queue.
    - Invited: hospital_head or department_head is caller, uses their facility.
    """
    claims = getattr(request.state, "claims", None)

    if claims:
        caller_role = claims["role"]
        if caller_role not in ("hospital_head", "department_head"):
            raise HTTPException(403, "hospital_head or department_head required to invite workers")
        facility_id = claims["facility_id"]
        created_by = claims["sub"]
    else:
        if not payload.facility_id:
            raise HTTPException(422, "facility_id is required for self-registration")
        facility_id = payload.facility_id
        created_by = "self-register"

    async with AdminSession() as session:
        async with session.begin():
            try:
                uid = await auth.register_worker(
                    session, username=payload.username, password=payload.password,
                    full_name=payload.full_name, occupation=payload.occupation,
                    phone=payload.phone, facility_id=facility_id,
                    primary_department=payload.primary_department,
                    created_by=created_by)
            except ValueError as e:
                raise HTTPException(409, str(e))
    return {"ok": True, "status": "pending_dept_head_verification", "user_id": uid}


# ── Verification ────────────────────────────────────────────────
@router.post("/verify/{user_id}")
async def verify_user(user_id: str, payload: VerifyPayload, request: Request):
    claims = request.state.claims
    async with AdminSession() as session:
        async with session.begin():
            target = (await session.execute(text("""
                SELECT u.role, u.facility_id, f.county
                FROM users u JOIN facilities f ON f.id = u.facility_id
                WHERE u.id = :id
            """), {"id": user_id})).mappings().first()
            if target is None:
                raise HTTPException(404, "user not found")

            caller_role = claims["role"]
            target_role = target["role"]

            if caller_role == "admin" and target_role == "county_officer":
                pass
            elif caller_role in ("county_officer", "county_officer") and target_role == "hospital_head":
                caller_county = (await session.execute(text(
                    "SELECT county FROM facilities WHERE id = :id"),
                    {"id": claims["facility_id"]})).scalar()
                if caller_county != target["county"]:
                    raise HTTPException(403, "user is outside your county")
            elif caller_role == "hospital_head" and target_role == "worker":
                if target["facility_id"] != claims["facility_id"]:
                    raise HTTPException(403, "worker is not at your facility")
            else:
                raise HTTPException(403, "you cannot verify this user")

            await auth.verify_user(session, user_id, claims["sub"], payload.approve)
    return {"ok": True, "approved": payload.approve}


# ── Profile / Me / Change Password / Delete ─────────────────────
@router.get("/me")
async def get_me(request: Request):
    claims = request.state.claims
    async with AdminSession() as session:
        p = await auth.get_profile(session, claims["sub"])
    if p is None:
        raise HTTPException(404, "user not found")
    return {**p.__dict__,
            "last_login_at": p.last_login_at.isoformat() if p.last_login_at else None,
            "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None}


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    primary_department: str | None = None
    occupation: str | None = None


@router.put("/me")
async def update_me(payload: ProfileUpdate, request: Request):
    claims = request.state.claims
    async with AdminSession() as session:
        async with session.begin():
            await auth.update_profile(session, claims["sub"], **payload.dict(exclude_none=True))
    return {"ok": True}


@router.post("/change-password")
async def change_password(payload: ChangePasswordPayload, request: Request):
    claims = request.state.claims
    async with AdminSession() as session:
        async with session.begin():
            ok = await auth.change_password(
                session, claims["sub"], payload.old_password, payload.new_password)
            if not ok:
                raise HTTPException(400, "current password incorrect")
    return {"ok": True}


@router.post("/delete-account")
async def delete_account(payload: DeleteAccountPayload, request: Request):
    claims = request.state.claims
    if claims["role"] == "admin":
        raise HTTPException(403, "admin accounts cannot self-delete")
    async with AdminSession() as session:
        async with session.begin():
            await auth.request_deletion(session, claims["sub"], payload.reason)
    return {"ok": True, "status": "deleted",
            "note": "Your data has been purged. You have been logged out."}
