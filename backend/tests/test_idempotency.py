import uuid
import pytest
from sqlalchemy import text
from app.db import AdminSession


@pytest.mark.asyncio
async def test_same_key_returns_same_response(client, facility_a, token_for):
    key = uuid.uuid4().hex
    t = token_for(facility_a)
    body = {"worker_id":"W-IDEM","department":"ED","shift":"night",
            "fatigue":8,"heat_exposure":7,"hours_worked":12.0,
            "symptoms":["headache","dizziness"]}
    h = {"Authorization":f"Bearer {t}","Idempotency-Key":key}
    r1 = await client.post("/api/bff/sync/checkins", headers=h, json=body)
    r2 = await client.post("/api/bff/sync/checkins", headers=h, json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    async with AdminSession() as s:
        n = (await s.execute(text(
            "SELECT count(*) FROM logs WHERE facility_id=:f"),
            {"f":facility_a})).scalar()
    assert n == 1
