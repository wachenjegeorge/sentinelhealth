from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.audit import append_audit
from app.db import AdminSession
from app.modules.auth import service as auth

router = APIRouter(prefix="/api/bff/admin/users", tags=["admin-users"])


def _require_officer(request: Request) -> dict:
    claims = request.state.claims
    if claims["role"] != "health_officer":
        raise HTTPException(403, "health_officer role required")
    return claims


async def _county_of(session, facility_id: str) -> str | None:
    return (await session.execute(text(
        "SELECT county FROM facilities WHERE id = :id"),
        {"id": facility_id})).scalar()


@router.get("/pending")
async def pending(request: Request):
    claims = _require_officer(request)
    async with AdminSession() as session:
        county = await _county_of(session, claims["facility_id"])
        if not county:
            raise HTTPException(500, "officer facility has no county")
        return {"pending": await auth.list_pending_in_county(session, county)}


@router.get("")
async def list_users(request: Request):
    claims = _require_officer(request)
    async with AdminSession() as session:
        county = await _county_of(session, claims["facility_id"])
        return {"users": await auth.list_users_in_county(session, county)}


@router.post("/{user_id}/approve")
async def approve(user_id: str, request: Request):
    claims = _require_officer(request)
    async with AdminSession() as session:
        async with session.begin():
            county = await _county_of(session, claims["facility_id"])
            target = (await session.execute(text("""
                SELECT u.id, u.facility_id, f.county, u.username
                FROM users u JOIN facilities f ON f.id = u.facility_id
                WHERE u.id = :id AND u.active = false
            """), {"id": user_id})).mappings().first()
            if target is None:
                raise HTTPException(404, "pending user not found")
            if target["county"] != county:
                raise HTTPException(403, "user is outside your county")
            await auth.approve_user(session, user_id, claims["sub"])
            await session.execute(text(
                "SELECT set_config('app.facility_id', :f, true)"),
                {"f": claims["facility_id"]})
            await append_audit(session, facility_id=claims["facility_id"],
                               actor=claims["username"], role="health_officer",
                               action="user.approve",
                               resource=f"users/{user_id}",
                               detail={"username": target["username"]})
    return {"ok": True}


@router.post("/{user_id}/reject")
async def reject(user_id: str, request: Request):
    claims = _require_officer(request)
    async with AdminSession() as session:
        async with session.begin():
            county = await _county_of(session, claims["facility_id"])
            target = (await session.execute(text("""
                SELECT u.id, u.username, f.county FROM users u
                JOIN facilities f ON f.id = u.facility_id
                WHERE u.id = :id AND u.active = false
            """), {"id": user_id})).mappings().first()
            if target is None:
                raise HTTPException(404, "pending user not found")
            if target["county"] != county:
                raise HTTPException(403, "user is outside your county")
            await auth.reject_user(session, user_id)
            await session.execute(text(
                "SELECT set_config('app.facility_id', :f, true)"),
                {"f": claims["facility_id"]})
            await append_audit(session, facility_id=claims["facility_id"],
                               actor=claims["username"], role="health_officer",
                               action="user.reject",
                               resource=f"users/{user_id}",
                               detail={"username": target["username"]})
    return {"ok": True}


class ResetPasswordPayload(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, payload: ResetPasswordPayload,
                         request: Request):
    claims = _require_officer(request)
    async with AdminSession() as session:
        async with session.begin():
            county = await _county_of(session, claims["facility_id"])
            target = (await session.execute(text("""
                SELECT u.id, u.username, f.county FROM users u
                JOIN facilities f ON f.id = u.facility_id
                WHERE u.id = :id
            """), {"id": user_id})).mappings().first()
            if target is None:
                raise HTTPException(404, "user not found")
            if target["county"] != county:
                raise HTTPException(403, "user is outside your county")
            await auth.reset_password(session, user_id, payload.new_password)
            await session.execute(text(
                "SELECT set_config('app.facility_id', :f, true)"),
                {"f": claims["facility_id"]})
            await append_audit(session, facility_id=claims["facility_id"],
                               actor=claims["username"], role="health_officer",
                               action="user.password_reset",
                               resource=f"users/{user_id}",
                               detail={"username": target["username"]})
    return {"ok": True}
