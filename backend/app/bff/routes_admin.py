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

    if role in ("county_officer", "health_officer"):
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

    if role in ("hospital_head", "department_head"):
        async with with_tenant(claims["facility_id"], role=role, user_id=claims["sub"]) as session:
            return await agg.overview_facility(session, claims["facility_id"])

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
