"""Ingestion - the ONLY writer of `logs`. County is derived from facility."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models import Log
from app.modules.facilities import service as fac
from app.modules.risk_engine import service as risk
from app.security import hash_worker_id


async def ingest(
    session: AsyncSession, *, facility_id: str, worker_id: str,
    department: str, shift: str, fatigue: int, heat_exposure: int,
    hours_worked: float, symptoms: list[str],
    ambient_heat_index: float = 30.0, staffing_density: float = 15.0,
) -> dict:
    county = await fac.county_of(session, facility_id)
    if county is None:
        raise HTTPException(422, f"unknown facility: {facility_id}")

    scored = risk.score(
        fatigue=fatigue, heat_exposure=heat_exposure,
        hours_worked=hours_worked, symptoms=symptoms,
        ambient_heat_index=ambient_heat_index,
        staffing_density=staffing_density)

    row = Log(
        facility_id=facility_id, county=county,
        worker_id_hash=hash_worker_id(worker_id),
        department=department, shift=shift,
        fatigue=fatigue, heat_exposure=heat_exposure,
        hours_worked=hours_worked, symptoms=symptoms,
        risk_score=scored["score"], risk_level=scored["level"],
        components=scored["components"],
        client_updated_at=datetime.now(timezone.utc))
    session.add(row)
    await session.flush()

    await append_audit(
        session, facility_id=facility_id,
        actor=row.worker_id_hash[:12], role="worker",
        action="checkin.create", resource=f"logs/{row.id}",
        detail={"risk_score": scored["score"], "level": scored["level"]})

    return {
        "log_id": str(row.id),
        "personal_score": scored["score"],
        "level": scored["level"],
        "drivers": scored["components"],
        "received_at": row.created_at.isoformat(),
    }
