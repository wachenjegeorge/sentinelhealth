from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.db import AdminSession
from app.modules.facilities import service as fac

router = APIRouter(prefix="/api/bff/facilities", tags=["facilities"])

async def _session():
    async with AdminSession() as s:
        yield s

@router.get("")
async def list_facilities(county: str | None = Query(None)):
    async for s in _session():
        return {"facilities": await fac.list_facilities(s, county)}

class CreateFacilityPayload(BaseModel):
    name: str = Field(min_length=3)
    keph_level: int = Field(ge=1, le=6)
    facility_type: str
    sub_county: str | None = None
    county: str | None = None

@router.post("")
async def create_facility(payload: CreateFacilityPayload, request: Request):
    claims = request.state.claims
    if claims["role"] not in ("county_officer", "county_officer", "admin"):
        raise HTTPException(403, "Only officers can add facilities")

    async with AdminSession() as session:
        # Determine county
        if claims["role"] == "admin":
            if not payload.county:
                raise HTTPException(400, "county is required when admin creates a facility")
            county = payload.county
        else:
            county = (await session.execute(text("SELECT county FROM facilities WHERE id=:id"), {"id": claims["facility_id"]})).scalar()

        fac_id = payload.name.lower().replace(" ", "-") + "-" + county.lower()[:3]
        
        await session.execute(text("""
            INSERT INTO facilities (id, name, county, sub_county, keph_level, facility_type, active)
            VALUES (:id, :n, :c, :s, :l, :t, true)
            ON CONFLICT (id) DO NOTHING
        """), {"id": fac_id, "n": payload.name, "c": county, "s": payload.sub_county, "l": payload.keph_level, "t": payload.facility_type})

    return {"ok": True, "facility_id": fac_id}
