from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/worker/shifts", tags=["shifts"])

class ShiftRequestPayload(BaseModel):
    schedule_id: str
    request_type: str
    reason: str

@router.post("/request")
async def request_shift_change(payload: ShiftRequestPayload, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="worker", user_id=claims["sub"]) as session:
        # Verify the shift belongs to this worker
        shift = (await session.execute(text("SELECT 1 FROM worker_schedules WHERE id = :id AND user_id = :u"), {"id": payload.schedule_id, "u": claims["sub"]})).scalar()
        if not shift:
            raise HTTPException(403, "You can only request changes for your own shifts.")

        await session.execute(text("""
            INSERT INTO shift_requests (user_id, facility_id, schedule_id, request_type, reason)
            VALUES (:u, :f, :s, :t, :r)
        """), {"u": claims["sub"], "f": claims["facility_id"], "s": payload.schedule_id, "t": payload.request_type, "r": payload.reason})
    return {"ok": True}
