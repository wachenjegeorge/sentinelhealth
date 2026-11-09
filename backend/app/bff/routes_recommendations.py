"""Officer → Hospital Head recommendations."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.db import AdminSession

router = APIRouter(prefix="/api/bff/admin/recommendations", tags=["recommendations"])


class NewRecommendation(BaseModel):
    facility_id: str = Field(min_length=2)
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=2000)
    severity: str = Field(pattern="^(low|medium|high)$")
    department: str | None = None
    related_wvi: float | None = None


@router.post("")
async def create_recommendation(payload: NewRecommendation, request: Request):
    claims = request.state.claims
    if claims["role"] not in ("county_officer", "admin"):
        raise HTTPException(403, "only officers can send recommendations")

    async with AdminSession() as session:
        async with session.begin():
            exists = (await session.execute(text(
                "SELECT 1 FROM facilities WHERE id = :id"
            ), {"id": payload.facility_id})).scalar()
            if not exists:
                raise HTTPException(404, "facility not found")

            rec_id = (await session.execute(text("""
                INSERT INTO recommendations
                  (facility_id, from_user_id, from_username, from_role,
                   to_role, department, severity, subject, message, related_wvi)
                VALUES (:fac, :uid, :uname, :role, 'hospital_head',
                        :dept, :sev, :subj, :msg, :wvi)
                RETURNING id
            """), {
                "fac": payload.facility_id, "uid": claims["sub"],
                "uname": claims.get("username", "officer"),
                "role": claims["role"], "dept": payload.department,
                "sev": payload.severity, "subj": payload.subject,
                "msg": payload.message, "wvi": payload.related_wvi,
            })).scalar()

    return {"ok": True, "id": str(rec_id)}


@router.get("")
async def list_recommendations(request: Request):
    claims = request.state.claims
    role = claims["role"]

    async with AdminSession() as session:
        if role == "hospital_head":
            rows = (await session.execute(text("""
                SELECT id, facility_id, from_username, from_role, department,
                       severity, subject, message, related_wvi, status,
                       created_at, acknowledged_at
                FROM recommendations
                WHERE facility_id = :fac AND to_role = 'hospital_head'
                ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                         created_at DESC LIMIT 100
            """), {"fac": claims["facility_id"]})).mappings().all()
        elif role in ("county_officer", "admin"):
            rows = (await session.execute(text("""
                SELECT id, facility_id, from_username, from_role, department,
                       severity, subject, message, related_wvi, status,
                       created_at, acknowledged_at
                FROM recommendations
                WHERE from_user_id = :uid
                ORDER BY created_at DESC LIMIT 100
            """), {"uid": claims["sub"]})).mappings().all()
        else:
            raise HTTPException(403, "no recommendations for this role")

    return {"recommendations": [{
        "id": str(r["id"]),
        "facility_id": r["facility_id"],
        "from_username": r["from_username"],
        "from_role": r["from_role"],
        "department": r["department"],
        "severity": r["severity"],
        "subject": r["subject"],
        "message": r["message"],
        "related_wvi": float(r["related_wvi"]) if r["related_wvi"] else None,
        "status": r["status"],
        "created_at": r["created_at"].isoformat(),
        "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
    } for r in rows]}


@router.post("/{rec_id}/acknowledge")
async def acknowledge(rec_id: str, request: Request):
    claims = request.state.claims
    if claims["role"] != "hospital_head":
        raise HTTPException(403, "hospital_head only")
    async with AdminSession() as session:
        async with session.begin():
            await session.execute(text("""
                UPDATE recommendations
                SET status = 'acknowledged', acknowledged_at = now(),
                    acknowledged_by = :by
                WHERE id = :id AND facility_id = :fac
            """), {"id": rec_id, "by": claims["sub"],
                   "fac": claims["facility_id"]})
    return {"ok": True}
