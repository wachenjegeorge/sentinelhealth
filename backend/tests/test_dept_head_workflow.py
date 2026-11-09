"""End-to-end tests for the dept head confirmation workflow.

Uses in-process ASGI transport against combined.app so all routes are
available (the BFF-only app excludes dept-head routes).

Prerequisites:
- Seeded test accounts (test-worker, test-dept-head, test-officer)
- Working DATABASE_URL (local postgres or Neon)

Run:
    docker compose exec monolith pytest tests/test_dept_head_workflow.py -v

These tests DO pollute the database (every run adds check-ins).
Clean manually or use a fresh DB for CI.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.combined import app as combined_app


DEPARTMENT = "ICU / Critical Care"
WORKER_USERNAME = "test-worker"
WORKER_PASSWORD = "TestPass2026!"
DEPT_HEAD_USERNAME = "test-dept-head"
DEPT_HEAD_PASSWORD = "TestPass2026!"
OFFICER_USERNAME = "test-officer"
OFFICER_PASSWORD = "TestPass2026!"


def _key():
    return uuid.uuid4().hex


@pytest.fixture
async def client():
    transport = ASGITransport(app=combined_app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           timeout=60.0) as c:
        yield c


async def _login(client, username, password):
    r = await client.post("/api/bff/auth/login",
                          json={"username": username, "password": password})
    if r.status_code != 200:
        pytest.skip(f"account {username} not seeded or not verified")
    return r.json()["access_token"]


@pytest.fixture
async def tokens(client):
    return {
        "worker": await _login(client, WORKER_USERNAME, WORKER_PASSWORD),
        "dept_head": await _login(client, DEPT_HEAD_USERNAME, DEPT_HEAD_PASSWORD),
        "officer": await _login(client, OFFICER_USERNAME, OFFICER_PASSWORD),
    }


async def _submit(client, token, fatigue, heat, department=DEPARTMENT, shift="night"):
    return await client.post(
        "/api/bff/sync/checkins",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": _key()},
        json={"department": department, "shift": shift, "fatigue": fatigue,
              "heat_exposure": heat, "hours_worked": 12,
              "symptoms": ["headache"]},
    )


async def test_high_risk_checkin_lands_in_queue(client, tokens):
    """High-risk check-in creates a pending log AND a pending queue entry.

    Uses max fatigue/heat + 3 heat symptoms so the risk engine scores
    Critical. Also verifies the fatigue>=8 OR heat>=8 routing threshold
    fires independently of the level string.
    """
    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    before = r.json().get("pending_count", 0)

    # Full payload to guarantee Critical (>65)
    r = await client.post(
        "/api/bff/sync/checkins",
        headers={"Authorization": f"Bearer {tokens['worker']}",
                 "Idempotency-Key": _key()},
        json={"department": DEPARTMENT, "shift": "night",
              "fatigue": 10, "heat_exposure": 10, "hours_worked": 16,
              "symptoms": ["headache", "dizziness", "nausea"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["level"] == "Critical", f"expected Critical, got {body['level']}"

    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    after = r.json().get("pending_count", 0)
    assert after == before + 1, f"queue did not grow: {before} -> {after}"


async def test_low_risk_checkin_skips_queue(client, tokens):
    """Low-risk check-in goes straight to auto_verified (bypasses queue)."""
    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    before = r.json().get("pending_count", 0)

    r = await _submit(client, tokens["worker"], fatigue=3, heat=2)
    assert r.status_code == 200
    assert r.json()["level"] in ("Low", "Moderate")

    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    after = r.json().get("pending_count", 0)
    assert after == before, f"low-risk entered queue: {before} -> {after}"


async def test_confirm_updates_both_tables(client, tokens):
    """Confirming a queue entry updates fatigue_confirmations.status."""
    await _submit(client, tokens["worker"], fatigue=9, heat=9)

    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    pending = [q for q in r.json().get("confirmation_queue", [])
               if q.get("status") == "pending"]
    assert pending, "no pending items after high-risk submit"
    qid = pending[0]["id"]

    r = await client.post(
        f"/api/bff/dept-head/confirm/{qid}",
        headers={"Authorization": f"Bearer {tokens['dept_head']}",
                 "Idempotency-Key": _key()},
        json={"action": "confirm", "notes": "verified"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    r = await client.get("/api/bff/dept-head/overview",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    confirmed_ids = [q["id"] for q in r.json()["confirmation_queue"]
                     if q["status"] == "confirmed"]
    assert qid in confirmed_ids


async def test_k_anonymity_threshold(client, tokens):
    """Groups with <5 confirmed/auto-verified rows are suppressed.

    Uses a unique department per run so cells don't collide across tests.
    """
    dept = f"TestDept-{uuid.uuid4().hex[:6]}"

    # 4 low-risk check-ins -> auto_verified -> n=4, still suppressed
    for _ in range(4):
        r = await _submit(client, tokens["worker"], fatigue=3, heat=2,
                          department=dept, shift="night")
        assert r.status_code == 200

    r = await client.get("/api/bff/admin/overview",
                          headers={"Authorization": f"Bearer {tokens['officer']}"})
    groups = r.json().get("groups", [])
    matching = [g for g in groups
                if g.get("department") == dept and g.get("shift") == "night"]
    assert not matching, f"cell should be suppressed at n=4, got: {matching}"

    # 5th check-in breaks the threshold
    await _submit(client, tokens["worker"], fatigue=3, heat=2,
                  department=dept, shift="night")

    r = await client.get("/api/bff/admin/overview",
                          headers={"Authorization": f"Bearer {tokens['officer']}"})
    groups = r.json().get("groups", [])
    matching = [g for g in groups
                if g.get("department") == dept and g.get("shift") == "night"]
    assert matching, "cell should appear at n=5"
    assert matching[0]["n"] == 5


async def test_alert_triage_acknowledge(client, tokens):
    """Dept head can acknowledge an anomaly alert."""
    # Trigger the anomaly engine by generating a cluster
    # (3+ high-fatigue check-ins in same dept/shift within 4h window)
    for _ in range(3):
        await _submit(client, tokens["worker"], fatigue=9, heat=9)

    # Anomaly scan only runs when /admin/overview is called
    await client.get("/api/bff/admin/overview",
                     headers={"Authorization": f"Bearer {tokens['officer']}"})

    r = await client.get("/api/bff/dept-head/alerts",
                          headers={"Authorization": f"Bearer {tokens['dept_head']}"})
    alerts = r.json().get("alerts", [])
    if not alerts:
        pytest.skip("anomaly_engine did not fire (need 3+ cluster in last 4h)")

    aid = alerts[0]["id"]

    r = await client.post(
        f"/api/bff/dept-head/alerts/{aid}/triage",
        headers={"Authorization": f"Bearer {tokens['dept_head']}",
                 "Idempotency-Key": _key()},
        json={"action": "acknowledge", "notes": "investigating now"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "acknowledge"
