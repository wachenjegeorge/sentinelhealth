from __future__ import annotations

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import with_tenant
from app.idempotency import run_with_serializable_retry, with_idempotency
from app.modules.ingestion.service import ingest

router = APIRouter(prefix="/api/bff/sync", tags=["sync"])


class CheckInPayload(BaseModel):
    department: str = Field(min_length=1, max_length=60)
    shift: str = Field(pattern="^(day|night)$")
    fatigue: int = Field(ge=1, le=10)
    heat_exposure: int = Field(ge=1, le=10)
    hours_worked: float = Field(ge=0, le=24)
    symptoms: list[str] = Field(default_factory=list)


@router.post("/checkins")
async def sync_checkin(payload: CheckInPayload, request: Request,
                       idempotency_key: str = Header(..., alias="Idempotency-Key")):
    claims = request.state.claims
    facility_id = claims["facility_id"]
    worker_id = claims["username"]  # authenticated identity, not client-supplied

    async def _work(session: AsyncSession):
        result = await ingest(
            session, facility_id=facility_id, worker_id=worker_id,
            department=payload.department, shift=payload.shift,
            fatigue=payload.fatigue, heat_exposure=payload.heat_exposure,
            hours_worked=payload.hours_worked, symptoms=payload.symptoms)

        # ── High-risk check-ins go through dept-head confirmation ──
        needs_review = (
            result.get("level") == "Critical"
            or payload.fatigue >= 8
            or payload.heat_exposure >= 8
        )
        if needs_review:
            from app.security import hash_worker_id
            row = (await session.execute(text("""
                SELECT id FROM logs
                WHERE facility_id = :f AND worker_id_hash = :h
                  AND created_at > now() - interval '10 seconds'
                ORDER BY created_at DESC LIMIT 1
            """), {"f": facility_id, "h": hash_worker_id(worker_id)})).mappings().first()

            if row:
                log_id = row["id"]
                await session.execute(text(
                    "UPDATE logs SET verification_status = 'pending' WHERE id = :id"
                ), {"id": log_id})
                from app.security import hash_worker_id as _hash
                await session.execute(text("""
                    INSERT INTO fatigue_confirmations
                        (facility_id, department, worker_id_hash,
                         worker_username, worker_display_name,
                         fatigue, heat_exposure, shift, status, log_id)
                    VALUES
                        (:f, :d, :wh, :wu, :wd, :fat, :heat, :sh, 'pending', :lid)
                """), {
                    "f": facility_id, "d": payload.department,
                    "wh": _hash(worker_id),
                    "wu": worker_id, "wd": worker_id,
                    "fat": payload.fatigue, "heat": payload.heat_exposure,
                    "sh": payload.shift, "lid": log_id,
                })
        return result

    async def _txn():
        async with with_tenant(facility_id) as session:
            return await with_idempotency(
                session, key=idempotency_key,
                facility_id=facility_id, work=_work)

    return await run_with_serializable_retry(_txn)
