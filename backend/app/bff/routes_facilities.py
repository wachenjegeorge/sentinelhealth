from fastapi import APIRouter, HTTPException, Query

from app.db import AdminSession  # facilities are public reference data
from app.modules.facilities import service as fac

router = APIRouter(prefix="/api/bff/facilities", tags=["facilities"])


async def _session():
    async with AdminSession() as s:
        yield s


@router.get("")
async def list_facilities(county: str | None = Query(None)):
    async for s in _session():
        return {"facilities": await fac.list_facilities(s, county)}


@router.get("/counties")
async def list_counties():
    async for s in _session():
        return {"counties": await fac.list_counties(s)}


@router.get("/{facility_id}")
async def get_facility(facility_id: str):
    async for s in _session():
        f = await fac.get_facility(s, facility_id)
        if f is None:
            raise HTTPException(404, "facility not found")
        return f
