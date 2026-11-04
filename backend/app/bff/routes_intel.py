"""Deep Intelligence API - analytical endpoints for the National/County workspace."""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from app.db import AdminSession
from app.modules.assistant import llm_client
import statistics

router = APIRouter(prefix="/api/bff/admin/intel", tags=["intel"])


def _check_county_access(claims: dict, county: str) -> None:
    if claims["role"] == "admin":
        return
    if claims.get("county") == county:
        return
    raise HTTPException(403, "County outside your scope")


# ── 1. County summary (KPIs) ─────────────────────────────
@router.get("/county/{county}/summary")
async def county_summary(county: str, request: Request):
    claims = request.state.claims
    _check_county_access(claims, county)

    async with AdminSession() as session:
        rows = (await session.execute(text("""
            SELECT facility_id, department, shift, day, n, avg_fatigue, avg_heat,
                   avg_score, p90_score, critical_share
            FROM agg_logs WHERE county = :c
        """), {"c": county})).mappings().all()

        facs = (await session.execute(text("""
            SELECT id, name, keph_level FROM facilities WHERE county = :c AND active
        """), {"c": county})).mappings().all()

        alerts = (await session.execute(text("""
            SELECT id, department, shift, alert_type, ai_protocol, created_at
            FROM autonomous_alerts WHERE county = :c AND status = 'active'
            ORDER BY created_at DESC
        """), {"c": county})).mappings().all()

    if not rows:
        return {
            "county": county,
            "facility_count": len(facs),
            "pooled_wvi": 0, "pooled_level": "Low",
            "total_reports": 0,
            "critical_facilities": 0,
            "active_alerts": len(alerts),
            "alerts": [dict(a) | {"created_at": a["created_at"].isoformat()} for a in alerts],
        }

    by_fac = {}
    for r in rows:
        by_fac.setdefault(r["facility_id"], []).append(r)

    fac_wvis = []
    for fac_id, recs in by_fac.items():
        total = sum(x["n"] for x in recs)
        if total < 5:
            continue
        weighted = sum(float(x["p90_score"]) * x["n"] for x in recs) / total
        fac_wvis.append(weighted)

    pooled = sum(fac_wvis) / len(fac_wvis) if fac_wvis else 0
    level = "Critical" if pooled >= 65 else "Moderate" if pooled >= 35 else "Low"
    total_reports = sum(r["n"] for r in rows)

    return {
        "county": county,
        "facility_count": len(facs),
        "facility_with_data": len(fac_wvis),
        "pooled_wvi": round(pooled, 1),
        "pooled_level": level,
        "max_facility_wvi": round(max(fac_wvis), 1) if fac_wvis else 0,
        "min_facility_wvi": round(min(fac_wvis), 1) if fac_wvis else 0,
        "std_deviation": round(statistics.stdev(fac_wvis), 1) if len(fac_wvis) > 1 else 0,
        "total_reports": total_reports,
        "critical_facilities": sum(1 for w in fac_wvis if w >= 65),
        "moderate_facilities": sum(1 for w in fac_wvis if 35 <= w < 65),
        "active_alerts": len(alerts),
        "alerts": [dict(a) | {"created_at": a["created_at"].isoformat()} for a in alerts],
    }


# ── 2. Facility deep-dive list ───────────────────────────
@router.get("/county/{county}/facilities")
async def county_facilities(county: str, request: Request):
    claims = request.state.claims
    _check_county_access(claims, county)

    async with AdminSession() as session:
        facs = (await session.execute(text("""
            SELECT id, name, keph_level, facility_type, sub_county
            FROM facilities WHERE county = :c AND active ORDER BY name
        """), {"c": county})).mappings().all()

        rows = (await session.execute(text("""
            SELECT facility_id, department, shift, n, avg_fatigue, avg_heat,
                   avg_score, p90_score, critical_share
            FROM agg_logs WHERE county = :c
        """), {"c": county})).mappings().all()

    by_fac = {}
    for r in rows:
        by_fac.setdefault(r["facility_id"], []).append(r)

    out = []
    for f in facs:
        recs = by_fac.get(f["id"], [])
        if not recs:
            out.append({
                "facility_id": f["id"], "name": f["name"],
                "keph_level": f["keph_level"], "facility_type": f["facility_type"],
                "sub_county": f["sub_county"], "suppressed": True,
                "wvi": None, "level": "No data", "reports": 0,
                "dept_count": 0, "top_dept": None,
                "avg_fatigue": None, "avg_heat": None,
                "critical_share": None, "trend": "flat",
            })
            continue

        total = sum(x["n"] for x in recs)
        if total < 5:
            out.append({
                "facility_id": f["id"], "name": f["name"],
                "keph_level": f["keph_level"], "facility_type": f["facility_type"],
                "sub_county": f["sub_county"], "suppressed": True,
                "wvi": None, "level": "Suppressed", "reports": total,
                "dept_count": len(set(x["department"] for x in recs)),
                "top_dept": None,
                "avg_fatigue": None, "avg_heat": None,
                "critical_share": None, "trend": "flat",
            })
            continue

        wvi = sum(float(x["p90_score"]) * x["n"] for x in recs) / total
        fatigue = sum(float(x["avg_fatigue"]) * x["n"] for x in recs) / total
        heat = sum(float(x["avg_heat"]) * x["n"] for x in recs) / total
        crit = sum(float(x["critical_share"]) * x["n"] for x in recs) / total
        level = "Critical" if wvi >= 65 else "Moderate" if wvi >= 35 else "Low"

        # Which dept is worst?
        dept_agg = {}
        for r in recs:
            dept_agg.setdefault(r["department"], []).append(r)
        worst = None
        for dname, drecs in dept_agg.items():
            dt = sum(x["n"] for x in drecs)
            if dt < 5: continue
            dwvi = sum(float(x["p90_score"]) * x["n"] for x in drecs) / dt
            if worst is None or dwvi > worst["wvi"]:
                worst = {"name": dname, "wvi": round(dwvi, 1), "reports": dt}

        out.append({
            "facility_id": f["id"], "name": f["name"],
            "keph_level": f["keph_level"], "facility_type": f["facility_type"],
            "sub_county": f["sub_county"], "suppressed": False,
            "wvi": round(wvi, 1), "level": level, "reports": total,
            "dept_count": len(dept_agg), "top_dept": worst,
            "avg_fatigue": round(fatigue, 1), "avg_heat": round(heat, 1),
            "critical_share": round(crit, 2), "trend": "flat",
        })

    out.sort(key=lambda x: -(x["wvi"] or -1))
    return {"county": county, "facilities": out}


# ── 3. Facility department depth ─────────────────────────
@router.get("/facility/{facility_id}/departments")
async def facility_departments(facility_id: str, request: Request):
    claims = request.state.claims
    if claims["role"] != "admin":
        async with AdminSession() as session:
            fac_county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id=:id"), {"id": facility_id})).scalar()
        if fac_county != claims.get("county"):
            raise HTTPException(403, "Facility outside your scope")

    async with AdminSession() as session:
        fac = (await session.execute(text("""
            SELECT id, name, keph_level, county, sub_county
            FROM facilities WHERE id=:id
        """), {"id": facility_id})).mappings().first()

        rows = (await session.execute(text("""
            SELECT department, shift, n, avg_fatigue, avg_heat, avg_score,
                   p90_score, critical_share, day
            FROM agg_logs WHERE facility_id = :f
        """), {"f": facility_id})).mappings().all()

    if not rows:
        return {"facility": dict(fac), "departments": [], "empty": True}

    by_dept = {}
    for r in rows:
        by_dept.setdefault(r["department"], []).append(r)

    departments = []
    for dname, recs in by_dept.items():
        total = sum(x["n"] for x in recs)
        if total < 5: continue
        wvi = sum(float(x["p90_score"]) * x["n"] for x in recs) / total
        fatigue = sum(float(x["avg_fatigue"]) * x["n"] for x in recs) / total
        heat = sum(float(x["avg_heat"]) * x["n"] for x in recs) / total
        crit = sum(float(x["critical_share"]) * x["n"] for x in recs) / total

        shifts = {}
        for r in recs:
            shifts.setdefault(r["shift"], {"reports": 0, "wvi_sum": 0})
            shifts[r["shift"]]["reports"] += r["n"]
            shifts[r["shift"]]["wvi_sum"] += float(r["p90_score"]) * r["n"]

        shift_data = [
            {"shift": s, "reports": v["reports"],
             "wvi": round(v["wvi_sum"] / v["reports"], 1)}
            for s, v in shifts.items() if v["reports"] >= 5
        ]

        departments.append({
            "department": dname, "wvi": round(wvi, 1),
            "level": "Critical" if wvi >= 65 else "Moderate" if wvi >= 35 else "Low",
            "reports": total, "avg_fatigue": round(fatigue, 1),
            "avg_heat": round(heat, 1), "critical_share": round(crit, 2),
            "shifts": shift_data,
        })

    departments.sort(key=lambda x: -x["wvi"])
    return {"facility": dict(fac), "departments": departments, "empty": False}


# ── 4. Trends + anomaly history ──────────────────────────
@router.get("/county/{county}/trends")
async def county_trends(county: str, request: Request):
    claims = request.state.claims
    _check_county_access(claims, county)

    async with AdminSession() as session:
        daily = (await session.execute(text("""
            SELECT date_trunc('day', created_at) AS day,
                   avg(risk_score)::numeric(5,1) AS avg_wvi,
                   count(*) AS reports,
                   avg(fatigue)::numeric(4,1) AS avg_fatigue,
                   avg(heat_exposure)::numeric(4,1) AS avg_heat
            FROM logs WHERE county = :c AND created_at >= now() - interval '30 days'
            GROUP BY 1 ORDER BY 1
        """), {"c": county})).mappings().all()

        anomalies = (await session.execute(text("""
            SELECT id, department, shift, alert_type, ai_protocol,
                   created_at, resolved_at, status
            FROM autonomous_alerts WHERE county = :c
            ORDER BY created_at DESC LIMIT 20
        """), {"c": county})).mappings().all()

    # Compare last 7 days vs previous 7
    if len(daily) >= 14:
        last7 = [float(d["avg_wvi"]) for d in daily[-7:]]
        prev7 = [float(d["avg_wvi"]) for d in daily[-14:-7]]
        direction = "improving" if sum(last7) < sum(prev7) else \
                    "worsening" if sum(last7) > sum(prev7) else "stable"
    else:
        direction = "insufficient_data"

    return {
        "county": county,
        "trend": [
            {"day": d["day"].strftime("%a %d"),
             "wvi": float(d["avg_wvi"]),
             "reports": d["reports"],
             "fatigue": float(d["avg_fatigue"]) if d["avg_fatigue"] else 0,
             "heat": float(d["avg_heat"]) if d["avg_heat"] else 0}
            for d in daily
        ],
        "direction": direction,
        "anomalies": [dict(a) | {
            "created_at": a["created_at"].isoformat(),
            "resolved_at": a["resolved_at"].isoformat() if a["resolved_at"] else None
        } for a in anomalies],
    }


# ── 5. AI heavy report ───────────────────────────────────
@router.post("/county/{county}/report")
async def generate_report(county: str, request: Request):
    claims = request.state.claims
    _check_county_access(claims, county)

    async with AdminSession() as session:
        # Gather all data
        facs = (await session.execute(text("""
            SELECT id, name, keph_level FROM facilities WHERE county = :c AND active
        """), {"c": county})).mappings().all()

        rows = (await session.execute(text("""
            SELECT facility_id, department, shift, n, p90_score, avg_fatigue, avg_heat
            FROM agg_logs WHERE county = :c
        """), {"c": county})).mappings().all()

        alerts = (await session.execute(text("""
            SELECT department, shift, alert_type, ai_protocol FROM autonomous_alerts
            WHERE county = :c AND status = 'active'
        """), {"c": county})).mappings().all()

    # Build summaries for the AI
    by_fac = {}
    for r in rows:
        by_fac.setdefault(r["facility_id"], []).append(r)

    fac_lines = []
    for f in facs:
        recs = by_fac.get(f["id"], [])
        if not recs:
            fac_lines.append(f"- {f['name']} (Level {f['keph_level']}): no aggregated data")
            continue
        total = sum(x["n"] for x in recs)
        if total < 5:
            fac_lines.append(f"- {f['name']} (Level {f['keph_level']}): suppressed (n={total} < 5)")
            continue
        wvi = sum(float(x["p90_score"]) * x["n"] for x in recs) / total
        fatigue = sum(float(x["avg_fatigue"]) * x["n"] for x in recs) / total
        heat = sum(float(x["avg_heat"]) * x["n"] for x in recs) / total
        fac_lines.append(
            f"- {f['name']} (Level {f['keph_level']}): WVI {wvi:.1f}, "
            f"{total} reports, avg fatigue {fatigue:.1f}/10, avg heat {heat:.1f}/10"
        )

    alert_lines = [
        f"- {a['department']} ({a['shift']}): {a['alert_type']} - {a['ai_protocol'][:100]}"
        for a in alerts
    ]

    prompt = f"""You are the National Director of Health Intelligence for Kenya's
Ministry of Health. Produce a comprehensive 5-section situation report for
{county} County's healthcare workforce.

DATA:
Facilities:
{chr(10).join(fac_lines) if fac_lines else 'No facilities registered'}

Active autonomous alerts:
{chr(10).join(alert_lines) if alert_lines else 'No active alerts'}

REPORT STRUCTURE (use Markdown with ## for section headers):

## 1. Executive Assessment
2-3 sentences summarizing the overall workforce vulnerability situation.
State whether the county is in a stable, watch, or crisis state.

## 2. Facility Risk Ranking
Rank the top 3 highest-risk facilities with their WVI scores. Explain WHY
each is at risk using the fatigue and heat data provided.

## 3. Structural Analysis
Identify patterns: are certain facility levels (Level 4 vs 5) more at risk?
Are specific departments clustering? Any staffing density concerns?

## 4. Root Cause Drivers
Which of the five risk drivers (Fatigue, Heat Strain, Symptom Load,
Staffing Strain, Biometric Drift) is dominating? Support with data.

## 5. Prescriptive Action Plan
Provide 4 concrete, actionable recommendations ordered by impact:
1. Immediate (this shift)
2. Short-term (this week)
3. Medium-term (this month)
4. Structural (this quarter)

Be specific. Reference numbers. Do not use phrases like "monitor" or "continue
to observe" — every recommendation must be an ACTION with a named responsible
party (County Health Management Team, Facility Head, etc.).
"""

    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        report = res["message"]["content"]
        engine = "groq"
    except Exception as e:
        report = f"""## Report Generation Failed

The AI engine is currently unavailable. Reason: {str(e)[:200]}

**Fallback Analysis:**

The county has {len(facs)} registered facilities. Manual review of the
facility ranking and trends tabs is recommended until AI is restored.
"""
        engine = "fallback"

    return {"county": county, "report": report, "engine": engine,
            "generated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat()}
