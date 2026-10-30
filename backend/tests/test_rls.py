import uuid
import pytest
from sqlalchemy import text
from app.db import with_tenant


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads(client, facility_a, facility_b, token_for):
    a = token_for(facility_a)
    r = await client.post("/api/bff/sync/checkins",
        headers={"Authorization":f"Bearer {a}","Idempotency-Key":uuid.uuid4().hex},
        json={"worker_id":"W-TEST-A","department":"ICU","shift":"day",
              "fatigue":5,"heat_exposure":4,"hours_worked":8.0,"symptoms":[]})
    assert r.status_code == 200, r.text
    async with with_tenant(facility_b) as s:
        rows = (await s.execute(text("SELECT facility_id FROM logs"))).all()
        assert all(row[0] == facility_b for row in rows), f"LEAK: {rows}"


@pytest.mark.asyncio
async def test_rls_requires_tenant_set():
    from app.db import AppSession
    try:
        async with AppSession() as s:
            async with s.begin():
                await s.execute(text("SELECT 1 FROM logs LIMIT 1"))
        assert False
    except RuntimeError:
        pass
