from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import with_tenant
from app.idempotency import run_with_serializable_retry, with_idempotency
from app.modules.ingestion.service import ingest

router = APIRouter(prefix="/api/bff/sync", tags=["sync"])


class CheckInPayload(BaseModel):
    worker_id: str = Field(min_length=3, max_length=40)
    department: str = Field(min_length=1, max_length=60)
    shift: str = Field(pattern="^(day|night)$")
    fatigue: int = Field(ge=1, le=10)
    heat_exposure: int = Field(ge=1, le=10)
    hours_worked: float = Field(ge=0, le=24)
    symptoms: list[str] = Field(default_factory=list)


@router.post("/checkins")
async def sync_checkin(payload: CheckInPayload, request: Request,
                       idempotency_key: str = Header(..., alias="Idempotency-Key")):
    facility = request.state.claims["facility_id"]

    async def _work(session: AsyncSession):
        return await ingest(session, facility_id=facility,
            worker_id=payload.worker_id, department=payload.department,
            shift=payload.shift, fatigue=payload.fatigue,
            heat_exposure=payload.heat_exposure,
            hours_worked=payload.hours_worked, symptoms=payload.symptoms)

    async def _txn():
        async with with_tenant(facility) as session:
            return await with_idempotency(session, key=idempotency_key,
                                          facility_id=facility, work=_work)

    return await run_with_serializable_retry(_txn)
