"""Idempotency test: same key = same response, exactly one row.

Uses a unique facility ID per test run so repeated runs never accumulate
state.
"""
import uuid
import pytest
from sqlalchemy import text
from app.db import AdminSession, SeedSession


async def _seed_facility(facility_id: str) -> None:
    async with SeedSession() as s:
        async with s.begin():
            await s.execute(text("""
                INSERT INTO facilities
                    (id, name, county, sub_county, keph_level,
                     facility_type, active)
                VALUES (:id, :n, 'Mombasa', 'Mvita', 4,
                        'Sub-County Hospital', true)
                ON CONFLICT (id) DO NOTHING
            """), {"id": facility_id, "n": f"Idem Test {facility_id[-6:]}"})


@pytest.mark.asyncio
async def test_same_key_returns_same_response(client, token_for):
    fac = f"test-fac-idem-{uuid.uuid4().hex[:8]}"
    await _seed_facility(fac)

    async with AdminSession() as s:
        async with s.begin():
            await s.execute(text('DELETE FROM logs WHERE facility_id = :f'), {'f': facility_a})
    key = uuid.uuid4().hex
    t = token_for(fac)
    body = {"worker_id": "W-IDEM", "department": "ED", "shift": "night",
            "fatigue": 8, "heat_exposure": 7, "hours_worked": 12.0,
            "symptoms": ["headache", "dizziness"]}
    h = {"Authorization": f"Bearer {t}", "Idempotency-Key": key}

    r1 = await client.post("/api/bff/sync/checkins", headers=h, json=body)
    r2 = await client.post("/api/bff/sync/checkins", headers=h, json=body)

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json() == r2.json(), "same key returned different responses"

    async with AdminSession() as s:
        n = (await s.execute(text(
            "SELECT count(*) FROM logs WHERE facility_id = :f"),
            {"f": fac})).scalar()

    assert n == 1, f"idempotency violated: expected 1 row, got {n}"
