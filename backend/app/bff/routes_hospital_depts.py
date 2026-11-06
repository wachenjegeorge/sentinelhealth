from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/hospital/departments", tags=["hospital-departments"])

@router.get("")
async def list_departments(request: Request):
    claims = request.state.claims
    if claims["role"] not in ("hospital_head", "county_officer", "admin"):
        raise HTTPException(403, "Facility management role required")

    async with with_tenant(claims["facility_id"], role=claims["role"], user_id=claims["sub"]) as session:
        # Get all departments that have check-ins + the dept heads
        rows = (await session.execute(text("""
            SELECT DISTINCT department FROM agg_logs WHERE facility_id = :f
        """), {"f": claims["facility_id"]})).scalars().all()

        heads = (await session.execute(text("""
            SELECT primary_department, full_name, username, phone
            FROM users 
            WHERE facility_id = :f AND role = 'department_head' AND active = true
        """), {"f": claims["facility_id"]})).mappings().all()

        head_map = {h["primary_department"]: dict(h) for h in heads}

        # Get WVI for each dept
        dept_stats = (await session.execute(text("""
            SELECT department, 
                   sum(n) as reports,
                   sum(p90_score * n) / sum(n) as wvi
            FROM agg_logs 
            WHERE facility_id = :f
            GROUP BY department
        """), {"f": claims["facility_id"]})).mappings().all()

        stats_map = {s["department"]: s for s in dept_stats}

    # Combine
    all_depts = set(rows) | set(head_map.keys())
    out = []
    for d in all_depts:
        stat = stats_map.get(d, {"reports": 0, "wvi": 0})
        wvi = float(stat["wvi"]) if stat["wvi"] else 0
        out.append({
            "department": d,
            "wvi": round(wvi, 1),
            "reports": int(stat["reports"]),
            "head": head_map.get(d),  # None if no head assigned
        })

    out.sort(key=lambda x: -x["wvi"])
    return {"facility_id": claims["facility_id"], "departments": out}
