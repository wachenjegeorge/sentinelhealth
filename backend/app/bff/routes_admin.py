from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AdminSession
from app.modules.aggregator import service as agg

router = APIRouter(prefix="/api/bff/admin", tags=["admin"])


async def admin_session():
    async with AdminSession() as s:
        yield s


@router.get("/overview")
async def overview(request: Request, session: AsyncSession = Depends(admin_session)):
    if request.state.claims["role"] != "health_officer":
        raise HTTPException(403, "health_officer role required")
    return await agg.overview(session)
