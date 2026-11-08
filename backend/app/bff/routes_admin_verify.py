"""Approval queues for each level of the hierarchy."""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from app.db import AdminSession
from app.modules.auth import service as auth

router = APIRouter(prefix="/api/bff/admin/verify", tags=["admin-verify"])


@router.get("/queue")
async def get_verify_queue(request: Request):
    claims = request.state.claims
    role = claims["role"]

    async with AdminSession() as session:
        if role == "admin":
            return {"queue": await auth.list_pending_officers(session),
                    "verifies": "county_officer"}

        if role == "county_officer":
            county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            return {"queue": await auth.list_pending_for_officer(session, county),
                    "verifies": "hospital_head"}

        if role == "hospital_head":
            # Hospital head sees BOTH pending dept heads AND pending workers
            # who don't have a dept head assigned yet
            dept_heads = (await session.execute(text("""
                SELECT id, username, full_name, occupation, phone,
                       primary_department, created_at
                FROM users
                WHERE role = 'department_head' AND verification_status = 'pending'
                  AND facility_id = :f
                ORDER BY created_at DESC
            """), {"f": claims["facility_id"]})).mappings().all()

            workers = (await session.execute(text("""
                SELECT id, username, full_name, occupation, phone,
                       primary_department, created_at
                FROM users
                WHERE role = 'worker' AND verification_status = 'pending'
                  AND facility_id = :f
                ORDER BY created_at DESC
            """), {"f": claims["facility_id"]})).mappings().all()

            queue = (
                [dict(r) | {"role": "department_head", "created_at": r["created_at"].isoformat()}
                 for r in dept_heads]
                + [dict(r) | {"role": "worker", "created_at": r["created_at"].isoformat()}
                   for r in workers]
            )
            return {"queue": queue, "verifies": "department_head_or_worker"}

        if role == "department_head":
            dept = (await session.execute(text(
                "SELECT primary_department FROM users WHERE id = :id"),
                {"id": claims["sub"]})).scalar()
            rows = (await session.execute(text("""
                SELECT id, username, full_name, occupation, phone,
                       primary_department, created_at
                FROM users
                WHERE role = 'worker' AND verification_status = 'pending'
                  AND facility_id = :f AND primary_department = :d
                ORDER BY created_at DESC
            """), {"f": claims["facility_id"], "d": dept})).mappings().all()
            return {"queue": [dict(r) | {"role": "worker", "created_at": r["created_at"].isoformat()} for r in rows],
                    "verifies": "worker"}

    raise HTTPException(403, "no verification queue for this role")
