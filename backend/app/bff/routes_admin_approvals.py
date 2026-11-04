from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/admin/approvals", tags=["approvals"])

@router.get("")
async def get_pending_requests(request: Request):
    claims = request.state.claims
    if claims["role"] != "health_officer":
        raise HTTPException(403, "Health officer required")
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        rows = (await session.execute(text("""
            SELECT r.id, r.request_type, r.reason, r.created_at, u.full_name, s.department, s.start_time, s.id as schedule_id
            FROM shift_requests r
            JOIN users u ON u.id = r.user_id
            JOIN worker_schedules s ON s.id = r.schedule_id
            WHERE r.facility_id = :f AND r.status = 'pending'
            ORDER BY r.created_at ASC
        """), {"f": claims["facility_id"]})).mappings().all()
    return {"requests": [dict(r) | {"created_at": r["created_at"].isoformat(), "start_time": r["start_time"].isoformat()} for r in rows]}

@router.post("/{request_id}/{action}")
async def handle_request(request_id: str, action: str, request: Request):
    claims = request.state.claims
    if action not in ("approve", "reject"):
        raise HTTPException(400, "Invalid action")
    
    status = "approved" if action == "approve" else "rejected"
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        # 1. Update the request status
        await session.execute(text("""
            UPDATE shift_requests SET status = :s WHERE id = :id AND facility_id = :f
        """), {"s": status, "id": request_id, "f": claims["facility_id"]})
        
        # 2. If approved, update the actual worker schedule status
        if action == "approve":
            # We pull the request_type (sick, leave, swap) and update the schedule
            req = (await session.execute(text("SELECT schedule_id, request_type FROM shift_requests WHERE id = :id"), {"id": request_id})).mappings().first()
            if req:
                new_sched_status = req["request_type"] # 'sick', 'leave', or 'swap'
                await session.execute(text("""
                    UPDATE worker_schedules SET status = :st WHERE id = :sid
                """), {"st": new_sched_status, "sid": req["schedule_id"]})
                
    return {"ok": True}
