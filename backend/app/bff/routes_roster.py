from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from app.db import with_tenant
from app.modules.assistant import llm_client
from datetime import datetime

router = APIRouter(prefix="/api/bff/admin/roster", tags=["roster"])

# KEPH Level to Department mapping
KEPH_DEPARTMENTS = {
    2: ["Outpatient (OPD)", "Community Health", "Pharmacy"],
    3: ["Outpatient (OPD)", "Maternity", "Community Health", "Pharmacy", "Laboratory"],
    4: ["Emergency Department", "Outpatient (OPD)", "Maternity", "Paediatrics", "Nursing Wards", "Laboratory", "Pharmacy"],
    5: ["Emergency Department", "ICU / Critical Care", "Maternity", "Paediatrics", "Outpatient (OPD)", "Laboratory", "Pharmacy", "Nursing Wards", "Kitchen & Laundry", "Community Health", "Waste & Mortuary"],
    6: ["Emergency Department", "ICU / Critical Care", "Maternity", "Paediatrics", "Outpatient (OPD)", "Laboratory", "Radiology", "Pharmacy", "Nursing Wards", "Kitchen & Laundry", "Community Health", "Waste & Mortuary", "Administration"]
}

@router.get("/departments")
async def get_departments(request: Request):
    claims = request.state.claims
    if claims["role"] != "health_officer":
        raise HTTPException(403, "health_officer role required")

    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        level = (await session.execute(text("SELECT keph_level FROM facilities WHERE id = :f"), {"f": claims["facility_id"]})).scalar()
        
    # Default to Level 4 if unknown
    depts = KEPH_DEPARTMENTS.get(level, KEPH_DEPARTMENTS[4])
    return {"departments": depts, "keph_level": level}

@router.get("")
async def get_roster(request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        rows = (await session.execute(text("""
            SELECT s.id, s.department, s.shift_type, s.start_time, s.end_time,
                   u.full_name, u.username
            FROM worker_schedules s
            JOIN users u ON u.id = s.user_id
            WHERE s.facility_id = :f AND s.start_time > now() - interval '12 hours'
            ORDER BY s.start_time ASC
        """), {"f": claims["facility_id"]})).mappings().all()
    return {"roster": [dict(r) | {"start_time": r["start_time"].isoformat(), "end_time": r["end_time"].isoformat()} for r in rows]}

class CreateShiftPayload(BaseModel):
    user_id: str
    department: str
    shift_type: str
    start_time: str
    end_time: str

@router.post("")
async def create_shift(payload: CreateShiftPayload, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        # Convert ISO strings to datetime
        start = datetime.fromisoformat(payload.start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(payload.end_time.replace("Z", "+00:00"))
        
        await session.execute(text("""
            INSERT INTO worker_schedules (user_id, facility_id, department, shift_type, start_time, end_time, status)
            VALUES (:u, :f, :d, :st, :start, :end, 'scheduled')
        """), {"u": payload.user_id, "f": claims["facility_id"], "d": payload.department, 
               "st": payload.shift_type, "start": start, "end": end})
    return {"ok": True}

class StrategyPayload(BaseModel):
    department: str
    shift: str
    current_wvi: float

@router.post("/strategy")
async def generate_strategy(payload: StrategyPayload, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        staff = (await session.execute(text("""
            SELECT u.full_name FROM worker_schedules s
            JOIN users u ON u.id = s.user_id
            WHERE s.facility_id = :f AND s.department = :d AND s.shift_type = :st AND s.start_time > now()
            LIMIT 5
        """), {"f": claims["facility_id"], "d": payload.department, "st": payload.shift})).scalars().all()
        
        staff_names = ", ".join(staff) if staff else "No specific staff scheduled yet"

        prompt = f"""
        You are an elite Predictive Health Strategist. The {payload.department} on the {payload.shift} shift is at a Critical WVI of {payload.current_wvi}.
        Staff: {staff_names}.
        Generate a 3-point Prescriptive Action Plan to prevent burnout.
        Return strict JSON with keys: "environmental", "fatigue", "roster".
        """
        try:
            res = await llm_client.chat([{"role": "user", "content": prompt}])
            import json
            content = res["message"]["content"].strip()
            if content.startswith("```json"): content = content[7:-3]
            strategy = json.loads(content)
        except Exception:
            strategy = {
                "environmental": f"Deploy a hydration station and portable fans to the {payload.department}.",
                "fatigue": "Enforce a strict 15-minute micro-break rotation every 90 minutes.",
                "roster": f"Review {staff_names.split(',')[0] if staff else 'staff'} recent fatigue scores; if >8, swap with a fresh day-shift worker."
            }
    return strategy
