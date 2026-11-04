from fastapi import APIRouter, Request
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/admin/impact", tags=["impact"])

@router.get("")
async def get_impact(request: Request):
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        # Count resolved alerts (interventions)
        interventions = (await session.execute(text("""
            SELECT count(*) FROM autonomous_alerts WHERE facility_id = :f AND status = 'resolved'
        """), {"f": claims["facility_id"]})).scalar() or 0

        # Count logged outcomes
        outcomes = (await session.execute(text("""
            SELECT count(*) FROM risk_outcomes WHERE facility_id = :f AND outcome = 'intervention'
        """), {"f": claims["facility_id"]})).scalar() or 0

        # Count total check-ins
        checkins = (await session.execute(text("""
            SELECT count(*) FROM logs WHERE facility_id = :f
        """), {"f": claims["facility_id"]})).scalar() or 0

    total_interventions = interventions + outcomes

    # ROI Logic (Simulated for the pitch)
    prevented_burnout = int(total_interventions * 0.85)
    overtime_saved_kes = prevented_burnout * 15000  # KES 15,000 per prevented sick day
    patient_safety_increase = min(99, 85 + (total_interventions * 1.2)) # Base 85% + improvement

    return {
        "total_interventions": total_interventions,
        "prevented_burnout": prevented_burnout,
        "overtime_saved_kes": overtime_saved_kes,
        "patient_safety_score": round(patient_safety_increase, 1),
        "total_checkins": checkins
    }
