from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.security import issue_token

router = APIRouter(prefix="/api/bff/worker", tags=["worker"])


class LoginPayload(BaseModel):
    worker_id: str
    facility_id: str
    role: str = "worker"


@router.post("/login")
async def login(payload: LoginPayload):
    if payload.role not in {"worker","health_officer"}:
        raise HTTPException(422, "invalid role")
    return {"access_token": issue_token(sub=payload.worker_id,
                                        role=payload.role,
                                        facility_id=payload.facility_id),
            "token_type": "bearer"}
