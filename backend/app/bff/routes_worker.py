from datetime import date, datetime, timezone
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import with_tenant
from app.modules.aggregator import service as agg

router = APIRouter(prefix="/api/bff/worker", tags=["worker"])


@router.get("/departments")
async def get_worker_departments(request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role=claims["role"], user_id=claims["sub"]) as session:
        level = (await session.execute(text("SELECT keph_level FROM facilities WHERE id = :f"), {"f": claims["facility_id"]})).scalar()
    
    # Import KEPH mapping from roster routes
    from app.bff.routes_roster import KEPH_DEPARTMENTS
    depts = KEPH_DEPARTMENTS.get(level, KEPH_DEPARTMENTS[4])
    return {"departments": depts, "keph_level": level}


@router.get("/dashboard")
async def get_dashboard(request: Request):
    claims = request.state.claims
    facility_id = claims["facility_id"]
    user_id = claims["sub"]

    # Use with_tenant WITH user_id so medical_history RLS lets us read own data
    async with with_tenant(facility_id, role="worker", user_id=user_id) as session:
        # 1. My schedule (next 5 shifts)
        schedules = (await session.execute(text("""
            SELECT id, department, shift_type, start_time, end_time, status
            FROM worker_schedules
            WHERE user_id = :u AND start_time >= now() - interval '1 day'
            ORDER BY start_time ASC LIMIT 5
        """), {"u": user_id})).mappings().all()
        
        sched_list = []
        for s in schedules:
            sched_list.append({
                "id": str(s["id"]), "department": s["department"],
                "shift_type": s["shift_type"], 
                "start_time": s["start_time"].isoformat(),
                "end_time": s["end_time"].isoformat(),
                "status": s["status"]
            })

        # 2. My recent check-ins (last 5)
        checkins = (await session.execute(text("""
            SELECT created_at, risk_score, risk_level, department, shift, fatigue, heat_exposure
            FROM logs
            WHERE worker_id_hash = (
                SELECT worker_id_hash FROM logs WHERE facility_id = :f LIMIT 1
            ) -- Fallback since we only have hash, we'll filter by hash of username
            ORDER BY created_at DESC LIMIT 5
        """), {"f": facility_id})).mappings().all()
        
        # Actually, to get *their* logs, we need the hash. Let's compute it.
        from app.security import hash_worker_id
        my_hash = hash_worker_id(claims["username"])
        
        my_checkins = (await session.execute(text("""
            SELECT created_at, risk_score, risk_level, department, shift, fatigue, heat_exposure
            FROM logs
            WHERE worker_id_hash = :h
            ORDER BY created_at DESC LIMIT 5
        """), {"h": my_hash})).mappings().all()

        checkin_list = []
        for c in my_checkins:
            checkin_list.append({
                "date": c["created_at"].isoformat(),
                "score": float(c["risk_score"]),
                "level": c["risk_level"],
                "department": c["department"],
                "shift": c["shift"],
                "fatigue": c["fatigue"],
                "heat": c["heat_exposure"]
            })

        # 3. My medical history
        meds = (await session.execute(text("""
            SELECT record_date, record_type, description, restricted_duty
            FROM medical_history
            WHERE user_id = :u ORDER BY record_date DESC LIMIT 5
        """), {"u": user_id})).mappings().all()
        
        med_list = []
        for m in meds:
            med_list.append({
                "date": m["record_date"].isoformat(),
                "type": m["record_type"],
                "description": m["description"],
                "restricted": m["restricted_duty"]
            })

        # 4. Facility aggregate risk (for context)
        overview = await agg.overview(session)
        # find their specific department
        dept_risk = None
        if claims.get("primary_department"):
            for g in overview["groups"]:
                if g["department"] == claims["primary_department"]:
                    dept_risk = g
                    break

    return {
        "schedules": sched_list,
        "checkins": checkin_list,
        "medical_history": med_list,
        "department_risk": dept_risk,
        "facility_pooled_wvi": overview["pooled_wvi"],
        "facility_level": overview["pooled_level"]
    }
