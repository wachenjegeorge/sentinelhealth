from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text
from app.db import with_tenant
from app.modules.assistant import llm_client

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

from pydantic import BaseModel as _BaseModel

class _AnalyzeBody(_BaseModel):
    department: str


@router.post("/analyze")
async def analyze_department(request: Request, payload: _AnalyzeBody):
    """Role-aware AI analysis. Department comes in POST body (slash-safe)."""
    claims = request.state.claims
    if claims["role"] not in ("hospital_head", "county_officer", "admin"):
        raise HTTPException(403, "Facility management role required")

    department = payload.department

    async with with_tenant(claims["facility_id"], role=claims["role"],
                           user_id=claims["sub"]) as session:
        groups = (await session.execute(text("""
            SELECT day, shift, n, p90_score, avg_fatigue, avg_heat, critical_share
            FROM agg_logs
            WHERE facility_id = :f AND department = :d
            ORDER BY day DESC LIMIT 30
        """), {"f": claims["facility_id"], "d": department})).mappings().all()

        alerts = (await session.execute(text("""
            SELECT alert_type, severity, shift, ai_protocol
            FROM autonomous_alerts
            WHERE facility_id = :f AND department = :d
              AND status IN ('active', 'acknowledged', 'escalated')
        """), {"f": claims["facility_id"], "d": department})).mappings().all()

        head = (await session.execute(text("""
            SELECT full_name, phone FROM users
            WHERE facility_id = :f AND primary_department = :d
              AND role = 'department_head' AND active
            LIMIT 1
        """), {"f": claims["facility_id"], "d": department})).mappings().first()

    total = sum(g["n"] for g in groups) or 0
    avg_wvi = (sum(float(g["p90_score"]) * g["n"] for g in groups) / total) if total else 0
    avg_fat = (sum(float(g["avg_fatigue"]) * g["n"] for g in groups) / total) if total else 0
    avg_heat = (sum(float(g["avg_heat"]) * g["n"] for g in groups) / total) if total else 0
    head_info = (head["full_name"] + " (" + str(head["phone"]) + ")") if head else "Not assigned"

    role = claims["role"]
    if role == "hospital_head":
        lens = "You are the Operational AI Co-Pilot for a HOSPITAL HEAD. Lens: staff reallocation, cross-department impact, escalation decisions, concrete operations this week."
    elif role == "county_officer":
        lens = "You are the COUNTY HEALTH OFFICER AI. Lens: peer facility comparison, county interventions, escalation to national."
    else:
        lens = "You are the NATIONAL DIRECTOR AI. Lens: systemic patterns, policy, national allocation."

    nl = chr(10)
    alert_lines = nl.join(
        "- " + a["alert_type"] + " (" + a["severity"] + ", " + a["shift"] + "): " + a["ai_protocol"][:100]
        for a in alerts
    ) or "None"

    prompt = (
        lens + nl + nl
        + "DEPARTMENT: " + department + nl
        + "FACILITY: " + claims["facility_id"] + nl + nl
        + "DATA (last 30 days):" + nl
        + "- Reports: " + str(total) + nl
        + "- Avg WVI: " + str(round(avg_wvi, 1)) + "/100" + nl
        + "- Avg fatigue: " + str(round(avg_fat, 1)) + "/10" + nl
        + "- Avg heat: " + str(round(avg_heat, 1)) + "/10" + nl
        + "- Dept head: " + head_info + nl
        + "- Active alerts: " + str(len(alerts)) + nl + nl
        + "Active alerts:" + nl + alert_lines + nl + nl
        + "Generate focused markdown with EXACTLY these 4 sections:" + nl + nl
        + "## Situation" + nl
        + "2-3 sentences. What is the current state? Reference numbers." + nl + nl
        + "## Top 3 Actions" + nl
        + "Numbered list. Each action MUST have WHO, WHAT, WHEN. Concrete. No monitor or consider." + nl + nl
        + "## Escalation" + nl
        + "Should this go to the county officer? Yes or No with reasoning." + nl + nl
        + "## Watchouts" + nl
        + "2 bullets of what could go wrong."
    )

    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        analysis = res["message"]["content"]
        engine = "groq"
    except Exception:
        analysis = (
            "## Analysis Unavailable" + nl + nl
            + "AI temporarily offline. Raw metrics:" + nl + nl
            + "- WVI: " + str(round(avg_wvi, 1)) + "/100" + nl
            + "- Fatigue: " + str(round(avg_fat, 1)) + "/10" + nl
            + "- Heat: " + str(round(avg_heat, 1)) + "/10" + nl
            + "- Reports: " + str(total) + nl
            + "- Alerts: " + str(len(alerts)) + nl
            + "- Dept head: " + head_info + nl + nl
            + "Review dashboard and act on alerts manually."
        )
        engine = "fallback"

    return {
        "department": department,
        "facility_id": claims["facility_id"],
        "analysis": analysis,
        "engine": engine,
        "metrics": {
            "total_reports": total,
            "avg_wvi": round(avg_wvi, 1),
            "avg_fatigue": round(avg_fat, 1),
            "avg_heat": round(avg_heat, 1),
            "head_assigned": head is not None,
            "active_alerts": len(alerts),
        },
    }
