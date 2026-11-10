import csv
import io
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.db import AdminSession, with_tenant
from app.modules.aggregator import service as agg
from app.modules.aggregator.anomaly_engine import scan_for_anomalies

router = APIRouter(prefix="/api/bff/admin", tags=["admin"])

@router.get("/overview")
async def overview(request: Request):
    claims = request.state.claims
    role = claims["role"]

    if role == "admin":
        async with AdminSession() as session:
            return await agg.overview_national(session)

    if role in ("county_officer", "county_officer"):
        async with with_tenant(claims["facility_id"], role=role, user_id=claims["sub"]) as session:
            county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            await scan_for_anomalies(session, claims["facility_id"], county)
            data = await agg.overview_county(session, county)
            alerts = (await session.execute(text("""
                SELECT id, department, shift, alert_type, ai_protocol, created_at
                FROM autonomous_alerts WHERE status = 'active'
                ORDER BY created_at DESC
            """))).mappings().all()
            data["autonomous_alerts"] = [dict(a) | {"created_at": a["created_at"].isoformat()} for a in alerts]
            return data

    if role == "hospital_head":
        async with with_tenant(claims["facility_id"], role=role, user_id=claims["sub"]) as session:
            data = await agg.overview_facility(session, claims["facility_id"])
            alerts = (await session.execute(text("""
                SELECT id, department, shift, alert_type, ai_protocol, status,
                       assigned_to_level, created_at
                FROM autonomous_alerts
                WHERE facility_id = :f
                  AND status IN ('active', 'escalated')
                  AND assigned_to_level IN ('hospital_head', 'county_officer')
                ORDER BY created_at DESC LIMIT 50
            """), {"f": claims["facility_id"]})).mappings().all()
            data["autonomous_alerts"] = [
                dict(a) | {"created_at": a["created_at"].isoformat()} for a in alerts
            ]
            return data

    if role == "department_head":
        # Department heads get their department-only view via /api/bff/dept-head/overview
        raise HTTPException(403, "department_head should use /api/bff/dept-head/overview")

    raise HTTPException(403, "no dashboard for this role")


# ── DRILL-DOWN ENDPOINTS ──
@router.get("/county/{county_name}")
async def drill_county(county_name: str, request: Request):
    claims = request.state.claims
    if claims["role"] != "admin":
        raise HTTPException(403, "Only admin can view other counties")
    
    async with AdminSession() as session:
        return await agg.overview_county(session, county_name)

@router.get("/facility/{facility_id}")
async def drill_facility(facility_id: str, request: Request):
    claims = request.state.claims
    role = claims["role"]
    
    # Verify permission
    if role != "admin":
        async with with_tenant(claims["facility_id"], role=role, user_id=claims["sub"]) as session:
            county = (await session.execute(text("SELECT county FROM facilities WHERE id=:id"), {"id": claims["facility_id"]})).scalar()
            target_county = (await session.execute(text("SELECT county FROM facilities WHERE id=:id"), {"id": facility_id})).scalar()
            if county != target_county:
                raise HTTPException(403, "Facility outside your scope")

    async with AdminSession() as session:
        return await agg.overview_facility(session, facility_id)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role=claims["role"], user_id=claims["sub"]) as session:
        await session.execute(text("UPDATE autonomous_alerts SET status = 'resolved', resolved_at = now() WHERE id = :id"), {"id": alert_id})
    return {"ok": True}


@router.get("/export")
async def export_csv(request: Request):
    claims = request.state.claims
    role = claims["role"]
    
    async with AdminSession() as session:
        if role == "admin":
            # Admin exports everything
            rows = (await session.execute(text("""
                SELECT l.created_at, f.county, f.name AS facility, l.department, l.shift,
                       l.fatigue, l.heat_exposure, l.risk_score, l.risk_level
                FROM logs l JOIN facilities f ON f.id = l.facility_id
                ORDER BY l.created_at DESC LIMIT 5000
            """))).mappings().all()
        else:
            # Officer exports their county
            county = (await session.execute(text("SELECT county FROM facilities WHERE id=:id"), {"id": claims["facility_id"]})).scalar()
            rows = (await session.execute(text("""
                SELECT l.created_at, f.county, f.name AS facility, l.department, l.shift,
                       l.fatigue, l.heat_exposure, l.risk_score, l.risk_level
                FROM logs l JOIN facilities f ON f.id = l.facility_id
                WHERE f.county = :c
                ORDER BY l.created_at DESC LIMIT 5000
            """), {"c": county})).mappings().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date","County","Facility","Department","Shift","Fatigue","Heat","WVI","Risk Level"])
    for r in rows:
        w.writerow([r["created_at"].strftime("%Y-%m-%d %H:%M"), r["county"], r["facility"], r["department"], r["shift"], r["fatigue"], r["heat_exposure"], r["risk_score"], r["risk_level"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="sentinel_export.csv"'})

@router.get("/forecast")
async def forecast(request: Request):
    """14-day WVI trend + 7-day projection + peer comparison (county scope)."""
    claims = request.state.claims
    if claims["role"] not in ("county_officer", "admin"):
        raise HTTPException(403, "county_officer or admin required")

    async with AdminSession() as session:
        if claims["role"] == "admin":
            county_q = request.query_params.get("county")
            if county_q:
                where = "county = :c"
                params = {"c": county_q}
            else:
                where = "1=1"
                params = {}
        else:
            county_q = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            where = "county = :c"
            params = {"c": county_q}

        rows = (await session.execute(text(f"""
            SELECT date_trunc('day', created_at) AS day,
                   avg(risk_score)::numeric(5,1) AS avg_wvi,
                   count(*) AS n
            FROM logs
            WHERE {where}
              AND verification_status IN ('confirmed','auto_verified')
              AND created_at >= now() - interval '14 days'
            GROUP BY 1 ORDER BY 1
        """), params)).mappings().all()

        national_median = (await session.execute(text("""
            SELECT avg(risk_score)::numeric(5,1)
            FROM logs
            WHERE verification_status IN ('confirmed','auto_verified')
              AND created_at >= now() - interval '14 days'
        """))).scalar()

    if len(rows) < 3:
        return {
            "county": county_q, "available": False,
            "reason": "insufficient_data",
            "points": len(rows),
            "trend": [{"day": r["day"].strftime("%Y-%m-%d"),
                       "wvi": float(r["avg_wvi"]), "n": r["n"]} for r in rows],
        }

    ys = [float(r["avg_wvi"]) for r in rows]
    n = len(ys)
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    slope = ((n * sum_xy - sum_x * sum_y) / denom) if denom else 0
    intercept = (sum_y - slope * sum_x) / n

    forecast_pts = []
    for i in range(n, n + 7):
        proj = max(0.0, min(100.0, slope * i + intercept))
        forecast_pts.append({"day_offset": i - n + 1, "projected_wvi": round(proj, 1)})

    current = round(ys[-1], 1)
    projected_7d = forecast_pts[-1]["projected_wvi"]
    direction = "worsening" if slope > 0.5 else ("improving" if slope < -0.5 else "stable")
    level = "Critical" if current >= 65 else ("Moderate" if current >= 35 else "Low")
    peer_delta = None
    if national_median is not None:
        peer_delta = round(current - float(national_median), 1)

    return {
        "county": county_q, "available": True,
        "current_wvi": current,
        "projected_7d_wvi": projected_7d,
        "slope_per_day": round(slope, 2),
        "trend_direction": direction,
        "level": level,
        "national_median": float(national_median) if national_median else None,
        "peer_delta": peer_delta,
        "trend": [{"day": r["day"].strftime("%Y-%m-%d"),
                   "wvi": float(r["avg_wvi"]), "n": r["n"]} for r in rows],
        "forecast": forecast_pts,
        "k_anonymity": 5,
    }

@router.get("/ai-brief")
async def ai_brief(request: Request):
    """4-section strategic brief for county officer / admin."""
    claims = request.state.claims
    role = claims["role"]
    nl = chr(10)

    async with AdminSession() as session:
        if role == "admin":
            county = request.query_params.get("county")
            where = "1=1" if not county else "county = :c"
            params = {} if not county else {"c": county}
        elif role == "hospital_head":
            county = None
            where = "facility_id = :f"
            params = {"f": claims["facility_id"]}
        else:
            county = (await session.execute(text(
                "SELECT county FROM facilities WHERE id = :id"),
                {"id": claims["facility_id"]})).scalar()
            where = "county = :c"
            params = {"c": county}

        rows = (await session.execute(text(f"""
            SELECT facility_id, county, department, shift,
                   sum(n) AS reports,
                   sum(p90_score * n) / sum(n) AS wvi
            FROM agg_logs WHERE {where}
            GROUP BY facility_id, county, department, shift
            HAVING sum(n) >= 5
        """), params)).mappings().all()

        fac_names = {r["id"]: r["name"] for r in (await session.execute(text(
            "SELECT id, name FROM facilities"
        ))).mappings().all()}

        alerts = (await session.execute(text(f"""
            SELECT department, shift, alert_type, severity
            FROM autonomous_alerts
            WHERE {where} AND status IN ('active','escalated')
            ORDER BY created_at DESC LIMIT 10
        """), params)).mappings().all()

    if not rows:
        return {
            "scope": county or "national",
            "engine": "fallback",
            "brief": "## No data yet" + nl + nl + "Not enough verified check-ins.",
            "metrics": {"groups": 0, "alerts": len(alerts)},
        }

    fac_wvi = {}
    for r in rows:
        fid = r["facility_id"]
        if fid not in fac_wvi:
            fac_wvi[fid] = {"total": 0.0, "weight": 0}
        fac_wvi[fid]["total"] += float(r["wvi"]) * float(r["reports"])
        fac_wvi[fid]["weight"] += float(r["reports"])

    top_facs = sorted(
        [{"id": k, "name": fac_names.get(k, k),
          "wvi": round(v["total"] / v["weight"], 1),
          "reports": v["weight"]}
         for k, v in fac_wvi.items()],
        key=lambda x: -x["wvi"]
    )[:5]

    total_reports = sum(f["reports"] for f in top_facs)
    pooled = (sum(f["wvi"] * f["reports"] for f in top_facs) / total_reports) if total_reports else 0
    critical_count = sum(1 for f in top_facs if f["wvi"] >= 65)

    from app.modules.assistant import llm_client
    alert_text = nl.join("- " + a["department"] + " (" + a["shift"] + "): " + a["alert_type"] for a in alerts) or "None"
    fac_text = nl.join(str(i+1) + ". " + f["name"] + ": WVI " + str(f["wvi"]) + ", " + str(f["reports"]) + " reports" for i, f in enumerate(top_facs))

    role_lens = "COUNTY HEALTH OFFICER" if role == "county_officer" else "NATIONAL DIRECTOR"
    prompt = (
        "You are the Strategic AI Co-Pilot for the " + role_lens + " of " + (county or "Kenya") + "." + nl + nl
        + "DATA (last 30 days):" + nl
        + "- Pooled WVI: " + str(round(pooled, 1)) + nl
        + "- Facilities at Critical: " + str(critical_count) + nl
        + "- Active alerts: " + str(len(alerts)) + nl + nl
        + "Top 5 facilities:" + nl + fac_text + nl + nl
        + "Active alerts:" + nl + alert_text + nl + nl
        + "Generate a strategic brief in markdown with EXACTLY these 4 sections:" + nl + nl
        + "## Situation" + nl
        + "2-3 sentences. Reference numbers." + nl + nl
        + "## Priority Facilities" + nl
        + "Top 2-3 facilities with WHY." + nl + nl
        + "## 3 Actions This Week" + nl
        + "Numbered. WHO, WHAT, WHEN." + nl + nl
        + "## Escalation" + nl
        + "Yes/No to national with one reason." + nl
    )

    try:
        res = await llm_client.chat([{"role": "user", "content": prompt}])
        brief = res["message"]["content"]
        engine = "groq"
    except Exception:
        brief = (
            "## Situation" + nl + nl
            + "Pooled WVI " + str(round(pooled, 1)) + ". " + str(critical_count) + " critical. " + str(len(alerts)) + " alerts." + nl + nl
            + "## Priority Facilities" + nl + nl + fac_text + nl + nl
            + "## 3 Actions This Week" + nl + nl
            + "1. **County CHMT**: Review staffing at " + (top_facs[0]["name"] if top_facs else "top facility") + " this week." + nl
            + "2. **Hospital Heads**: Confirm high-risk check-ins by end of shift." + nl
            + "3. **County CHMT**: Deploy hydration protocols to ICU and ED." + nl + nl
            + "## Escalation" + nl + nl
            + ("Yes - national support recommended." if critical_count >= 2 else "No - manageable at county.")
        )
        engine = "fallback"

    return {
        "scope": county or "national",
        "engine": engine,
        "brief": brief,
        "metrics": {
            "groups": len(rows),
            "facilities": len(fac_wvi),
            "critical_facilities": critical_count,
            "pooled_wvi": round(pooled, 1),
            "alerts": len(alerts),
        },
        "top_facilities": top_facs,
    }
