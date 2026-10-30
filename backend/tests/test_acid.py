import uuid
import pytest
from sqlalchemy import text
from app.db import AdminSession, with_tenant
from app.idempotency import with_idempotency


@pytest.mark.asyncio
async def test_failed_work_leaves_no_trace(facility_a):
    key = uuid.uuid4().hex
    async def boom(_s):
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        async with with_tenant(facility_a) as s:
            await with_idempotency(s, key=key, facility_id=facility_a, work=boom)
    async with AdminSession() as s:
        n = (await s.execute(text(
            "SELECT count(*) FROM idempotency_ledger WHERE key=:k"),
            {"k":key})).scalar()
    assert n == 0
