"""Fix phantom health_officer role, county JWT, dept_head verification chain."""
import pathlib, re

ROOT = pathlib.Path(".")

def sed(path, replacements, label=""):
    p = ROOT / path
    if not p.exists(): print(f"SKIP {path}"); return
    s = p.read_text(encoding="utf-8"); o = s; n = 0
    for old, new in replacements:
        if old in s: n += s.count(old); s = s.replace(old, new)
    if s != o:
        p.write_text(s, encoding="utf-8"); print(f"OK {path} ({n}) {label}")
    else:
        print(f"=  {path} (no match) {label}")

# ─────────────────────────────────────────────────────────────
# 1. security.py — add county to JWT
# ─────────────────────────────────────────────────────────────
sec = ROOT / "backend/app/security.py"
if sec.exists():
    s = sec.read_text(encoding="utf-8")
    s = s.replace(
        'def issue_token(user_id: str, username: str, role: str,\n                facility_id: str, ttl_minutes: int = 720) -> str:',
        'def issue_token(user_id: str, username: str, role: str,\n                facility_id: str, county: str | None = None,\n                ttl_minutes: int = 720) -> str:'
    )
    s = s.replace(
        '"sub": user_id, "username": username, "role": role,\n        "facility_id": facility_id,',
        '"sub": user_id, "username": username, "role": role,\n        "facility_id": facility_id, "county": county,'
    )
    sec.write_text(s, encoding="utf-8")
    print("OK security.py: JWT county claim")

# ─────────────────────────────────────────────────────────────
# 2. routes_auth.py — pass county to issue_token
# ─────────────────────────────────────────────────────────────
sed("backend/app/bff/routes_auth.py", [
    ('token = issue_token(user_id=result.user_id, username=result.username,\n                        role=result.role, facility_id=result.facility_id)',
     'token = issue_token(user_id=result.user_id, username=result.username,\n                        role=result.role, facility_id=result.facility_id,\n                        county=result.county)'),
    ('    token = issue_token(\n        user_id=user_row["id"], username=user_row["username"],\n        role=user_row["role"], facility_id=user_row["facility_id"]\n    )',
     '    token = issue_token(\n        user_id=user_row["id"], username=user_row["username"],\n        role=user_row["role"], facility_id=user_row["facility_id"],\n        county=county\n    )'),
], "(county in JWT)")

# ─────────────────────────────────────────────────────────────
# 3. Replace health_officer → county_officer in all backend routes
# ─────────────────────────────────────────────────────────────
BACKEND_ROUTES = [
    "backend/app/bff/routes_admin.py",
    "backend/app/bff/routes_admin_verify.py",
    "backend/app/bff/routes_assistant.py",
    "backend/app/bff/routes_facilities.py",
    "backend/app/bff/routes_impact.py",
    "backend/app/bff/routes_incidents.py",
    "backend/app/bff/routes_roster.py",
    "backend/app/bff/routes_users.py",
    "backend/app/bff/routes_auth.py",
]
for f in BACKEND_ROUTES:
    sed(f, [
        ('"health_officer"', '"county_officer"'),
        ("'health_officer'", "'county_officer'"),
        ('role="health_officer"', 'role="county_officer"'),
        ('role == "health_officer"', 'role == "county_officer"'),
        ('role != "health_officer"', 'role != "county_officer"'),
    ], "(phantom role)")

# ─────────────────────────────────────────────────────────────
# 4. routes_intel.py — fix _check_county_access to use JWT county claim
# ─────────────────────────────────────────────────────────────
sed("backend/app/bff/routes_intel.py", [
    ('def _check_county_access(claims: dict, county: str) -> None:\n    if claims["role"] == "admin":\n        return\n    if claims.get("county") == county:\n        return\n    raise HTTPException(403, "County outside your scope")',
     'def _check_county_access(claims: dict, county: str) -> None:\n    """Allow admin. Allow county_officer whose JWT county matches."""\n    if claims["role"] == "admin":\n        return\n    jwt_county = claims.get("county")\n    if jwt_county and jwt_county.lower() == county.lower():\n        return\n    raise HTTPException(403, f"County \'{county}\' is outside your scope")'),
], "(intel county)")

# ─────────────────────────────────────────────────────────────
# 5. routes_auth.py — WorkerReg add facility_id; endpoint handle self-registration
# ─────────────────────────────────────────────────────────────
auth_file = ROOT / "backend/app/bff/routes_auth.py"
if auth_file.exists():
    s = auth_file.read_text(encoding="utf-8")

    # 5a. WorkerReg schema
    s = s.replace(
        'class WorkerReg(BaseModel):\n    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")\n    password: str = Field(min_length=8, max_length=128)\n    full_name: str = Field(min_length=2, max_length=120)\n    occupation: str = Field(min_length=2, max_length=80)\n    phone: str = Field(min_length=7, max_length=20)\n    primary_department: str = Field(min_length=2, max_length=60)',
        'class WorkerReg(BaseModel):\n    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")\n    password: str = Field(min_length=8, max_length=128)\n    full_name: str = Field(min_length=2, max_length=120)\n    occupation: str = Field(min_length=2, max_length=80)\n    phone: str = Field(min_length=7, max_length=20)\n    primary_department: str = Field(min_length=2, max_length=60)\n    facility_id: str | None = None'
    )

    # 5b. register_worker handler — allow self-register
    old_handler = '''@router.post("/register/worker")
async def register_worker(payload: WorkerReg, request: Request):
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
                    primary_department=payload.primary_department,
                    created_by=claims["sub"])
            except ValueError as e:
                raise HTTPException(409, str(e))
    return {"ok": True, "status": "pending_head_verification", "user_id": uid}'''

    new_handler = '''@router.post("/register/worker")
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
    return {"ok": True, "status": "pending_dept_head_verification", "user_id": uid}'''

    if old_handler in s:
        s = s.replace(old_handler, new_handler)
        print("OK routes_auth.py: register_worker self-service")
    else:
        print("=  routes_auth.py: register_worker (no match)")

    auth_file.write_text(s, encoding="utf-8")

# ─────────────────────────────────────────────────────────────
# 6. routes_auth.py — verify_user add dept_head cases
# ─────────────────────────────────────────────────────────────
auth_file = ROOT / "backend/app/bff/routes_auth.py"
if auth_file.exists():
    s = auth_file.read_text(encoding="utf-8")

    old_case = '''            if caller_role == "admin" and target_role == "county_officer":
                pass
            elif caller_role in ("county_officer",) and target_role == "hospital_head":
                caller_county = (await session.execute(text(
                    "SELECT county FROM facilities WHERE id = :id"),
                    {"id": claims["facility_id"]})).scalar()
                if caller_county != target["county"]:
                    raise HTTPException(403, "user is outside your county")
            elif caller_role == "hospital_head" and target_role == "worker":
                if target["facility_id"] != claims["facility_id"]:
                    raise HTTPException(403, "worker is not at your facility")
            else:
                raise HTTPException(403, "you cannot verify this user")'''

    new_case = '''            if caller_role == "admin" and target_role == "county_officer":
                pass
            elif caller_role == "county_officer" and target_role == "hospital_head":
                caller_county = (await session.execute(text(
                    "SELECT county FROM facilities WHERE id = :id"),
                    {"id": claims["facility_id"]})).scalar()
                if caller_county != target["county"]:
                    raise HTTPException(403, "user is outside your county")
            elif caller_role == "hospital_head" and target_role == "department_head":
                if target["facility_id"] != claims["facility_id"]:
                    raise HTTPException(403, "dept head is not at your facility")
            elif caller_role == "hospital_head" and target_role == "worker":
                if target["facility_id"] != claims["facility_id"]:
                    raise HTTPException(403, "worker is not at your facility")
            elif caller_role == "department_head" and target_role == "worker":
                if target["facility_id"] != claims["facility_id"]:
                    raise HTTPException(403, "worker is not at your facility")
                caller_dept = (await session.execute(text(
                    "SELECT primary_department FROM users WHERE id = :id"),
                    {"id": claims["sub"]})).scalar()
                target_dept = (await session.execute(text(
                    "SELECT primary_department FROM users WHERE id = :id"),
                    {"id": user_id})).scalar()
                if caller_dept != target_dept:
                    raise HTTPException(403, "worker is not in your department")
            else:
                raise HTTPException(403, "you cannot verify this user")'''

    if old_case in s:
        s = s.replace(old_case, new_case)
        print("OK routes_auth.py: verify_user dept_head chain")
    else:
        print("=  routes_auth.py: verify_user (no match — check patterns)")
    auth_file.write_text(s, encoding="utf-8")

# ─────────────────────────────────────────────────────────────
# 7. middleware.py — add worker self-register to public endpoints
# ─────────────────────────────────────────────────────────────
sed("backend/app/bff/middleware.py", [
    ('PUBLIC_ENDPOINTS = {\n    "/api/bff/auth/login",\n    "/api/bff/auth/register",\n    "/api/bff/auth/register/county-officer",\n}',
     'PUBLIC_ENDPOINTS = {\n    "/api/bff/auth/login",\n    "/api/bff/auth/register",\n    "/api/bff/auth/register/worker",\n    "/api/bff/auth/register/county-officer",\n}'),
], "(public worker reg)")

