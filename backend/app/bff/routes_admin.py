from fastapi import APIRouter, HTTPException, Request

from app.db import with_tenant
from app.modules.aggregator import service as agg

router = APIRouter(prefix="/api/bff/admin", tags=["admin"])


@router.get("/overview")
async def overview(request: Request, window_hours: int = 24):
    claims = request.state.claims
    if claims["role"] != "health_officer":
        raise HTTPException(403, "health_officer role required")

    # role= must be passed, otherwise with_tenant defaults to "worker"
    # and the RLS policy uses the facility branch instead of the county
    # branch, causing an officer to see only their own facility.
    async with with_tenant(claims["facility_id"], role=claims["role"]) as session:
        return await agg.overview(session, window_hours)
