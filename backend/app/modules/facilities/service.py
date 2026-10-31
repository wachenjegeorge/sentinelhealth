"""Facilities - public reference data. No RLS, all authenticated users see all."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_facilities(session: AsyncSession, county: str | None = None) -> list[dict]:
    sql = """
        SELECT id, name, county, sub_county, keph_level, facility_type
        FROM facilities WHERE active = true
    """
    params: dict = {}
    if county:
        sql += " AND county = :county"
        params["county"] = county
    sql += " ORDER BY county, keph_level DESC, name"

    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


async def get_facility(session: AsyncSession, facility_id: str) -> dict | None:
    row = (await session.execute(text("""
        SELECT id, name, county, sub_county, keph_level, facility_type
        FROM facilities WHERE id = :id AND active = true
    """), {"id": facility_id})).mappings().first()
    return dict(row) if row else None


async def county_of(session: AsyncSession, facility_id: str) -> str | None:
    row = (await session.execute(text(
        "SELECT county FROM facilities WHERE id = :id"
    ), {"id": facility_id})).scalar()
    return row


async def list_counties(session: AsyncSession) -> list[str]:
    rows = (await session.execute(text(
        "SELECT DISTINCT county FROM facilities WHERE active = true ORDER BY county"
    ))).scalars().all()
    return list(rows)
