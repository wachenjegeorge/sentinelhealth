from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/admin/incidents", tags=["incidents"])

@router.get("")
async def list_incidents(request: Request):
    claims = request.state.claims
    if claims["role"] != "county_officer":
        raise HTTPException(403, "health_officer role required")

    async with with_tenant(claims["facility_id"], role=claims["role"], user_id=claims["sub"]) as session:
        # Get resolved alerts (past interventions)
        alerts = (await session.execute(text("""
            SELECT id, department, shift, alert_type, ai_protocol, created_at, resolved_at
            FROM autonomous_alerts
            WHERE facility_id = :f AND status = 'resolved'
            ORDER BY resolved_at DESC LIMIT 50
        """), {"f": claims["facility_id"]})).mappings().all()

        # Get recorded outcomes
        outcomes = (await session.execute(text("""
            SELECT county, department, shift, day, predicted_wvi, outcome, notes, created_at
            FROM risk_outcomes
            WHERE facility_id = :f
            ORDER BY created_at DESC LIMIT 50
        """), {"f": claims["facility_id"]})).mappings().all()

    return {
        "resolved_alerts": [dict(a) | {"created_at": a["created_at"].isoformat(), "resolved_at": a["resolved_at"].isoformat() if a["resolved_at"] else None} for a in alerts],
        "outcomes": [dict(o) | {"day": str(o["day"]), "created_at": o["created_at"].isoformat()} for o in outcomes]
    }
