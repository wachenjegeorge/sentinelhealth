from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import AdminSession
from app.modules.auth import service as auth
from app.security import issue_token

router = APIRouter(prefix="/api/bff/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    facility_id: str
    county: str


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginPayload):
    async with AdminSession() as session:
        result = await auth.authenticate(session, payload.username, payload.password)
        if result is None:
            raise HTTPException(401, "invalid credentials")

        # Look up county for the response (frontend uses it to route)
        from sqlalchemy import text
        county = (await session.execute(
            text("SELECT county FROM facilities WHERE id = :id"),
            {"id": result.facility_id},
        )).scalar()
        if county is None:
            raise HTTPException(500, "user has invalid facility")

    token = issue_token(
        user_id=result.user_id,
        username=result.username,
        role=result.role,
        facility_id=result.facility_id,
    )
    return LoginResponse(
        access_token=token, role=result.role,
        facility_id=result.facility_id, county=county,
    )
