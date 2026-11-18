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
    cognitive_fatigue: int | None = None,
    mental_clarity: int | None = None,
    stress: int | None = None,
    sleep_quality: int | None = None,
    sleep_hours: float | None = None,
) -> dict:
    county = await fac.county_of(session, facility_id)
    if county is None:
        raise HTTPException(422, f"unknown facility: {facility_id}")

    scored = risk.score(
        fatigue=fatigue, heat_exposure=heat_exposure,
        hours_worked=hours_worked, symptoms=symptoms,
        ambient_heat_index=ambient_heat_index,
        staffing_density=staffing_density)

    cwi_result = None
    cognitive_components = None
    if all(v is not None for v in
           (cognitive_fatigue, mental_clarity, stress, sleep_quality, sleep_hours)):
        from app.modules.cognitive.service import compute_cwi
        cwi_result = compute_cwi(
            cognitive_fatigue=int(cognitive_fatigue),
            mental_clarity=int(mental_clarity),
            stress=int(stress),
            sleep_quality=int(sleep_quality),
            sleep_hours=float(sleep_hours))
        cognitive_components = cwi_result["components"]

    row = Log(
        facility_id=facility_id, county=county,
        worker_id_hash=hash_worker_id(worker_id),
        department=department, shift=shift,
        fatigue=fatigue, heat_exposure=heat_exposure,
        hours_worked=hours_worked, symptoms=symptoms,
        risk_score=scored["score"], risk_level=scored["level"],
        components=scored["components"],
        cognitive_fatigue=cognitive_fatigue,
        mental_clarity=mental_clarity,
        stress=stress,
        sleep_quality=sleep_quality,
        sleep_hours=sleep_hours,
        cwi=cwi_result["cwi"] if cwi_result else None,
        cwi_level=cwi_result["level"] if cwi_result else None,
        cognitive_components=cognitive_components,
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
        "cwi": cwi_result["cwi"] if cwi_result else None,
        "cwi_level": cwi_result["level"] if cwi_result else None,
        "cwi_drivers": cognitive_components,
        "received_at": row.created_at.isoformat(),
    }
