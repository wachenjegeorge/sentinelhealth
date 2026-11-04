"""Approval queues for each level of the hierarchy."""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from app.db import AdminSession
from app.modules.auth import service as auth

router = APIRouter(prefix="/api/bff/admin/verify", tags=["admin-verify"])


@router.get("/queue")
async def get_verify_queue(request: Request):
    """Returns pending users that the caller is responsible for verifying."""
    claims = request.state.claims
    role = claims["role"]

    async with AdminSession() as session:
        if role == "admin":
            # Admin verifies county officers
            return {"queue": await auth.list_pending_officers(session),
                    "verifies": "county_officer"}

        if role in ("county_officer", "health_officer"):
            # Officer verifies hospital heads in their county
            county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            return {"queue": await auth.list_pending_for_officer(session, county),
                    "verifies": "hospital_head"}

        if role == "hospital_head":
            # Head verifies workers at their facility
            return {"queue": await auth.list_pending_for_head(session, claims["facility_id"]),
                    "verifies": "worker"}

    raise HTTPException(403, "no verification queue for this role")
