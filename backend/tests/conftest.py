"""Test fixtures for SentinelHealth backend.

NOTE on facility IDs: sync/checkins validates that the facility exists
(ingest raises "unknown facility: X" otherwise). So the facility_a /
facility_b fixtures below use FIXED IDs and seed those facilities on
every call (idempotent via ON CONFLICT DO NOTHING). This mirrors what
production looks like — real facilities, not random strings.
"""
import os, uuid
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sentinel:change-me@localhost:6432/sentinel")
os.environ.setdefault("DATABASE_URL_ADMIN", "postgresql+asyncpg://sentinel_admin:change-me@localhost:6432/sentinel")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("WORKER_ID_PEPPER", "test-pepper")

from app.bff.app import app as bff_app
from app.security import issue_token


TEST_FAC_A = "test-fac-a-rls"
TEST_FAC_B = "test-fac-b-rls"


@pytest.fixture
async def client():
    t = ASGITransport(app=bff_app)
    async with AsyncClient(transport=t, base_url="http://bff") as c:
        yield c


async def _seed_facility(facility_id: str, name: str):
    """Insert a test facility if it does not exist.

    Uses SeedSession (DATABASE_URL_MIGRATION = neondb_owner) because
    test setup is administrative work that needs DDL/DML rights.
    app_user only has SELECT on `facilities` by design — writes happen
    through routes_facilities.py under with_tenant(county_officer) with
    RLS policies. Using AdminSession here would couple tests to the
    runtime admin role, which is a fragile assumption.
    """
    from sqlalchemy import text
    from app.db import SeedSession
    async with SeedSession() as s:
        async with s.begin():
            await s.execute(text("""
                INSERT INTO facilities
                    (id, name, county, sub_county, keph_level,
                     facility_type, active)
                VALUES (:id, :n, 'Mombasa', 'Mvita', 4,
                        'Sub-County Hospital', true)
                ON CONFLICT (id) DO NOTHING
            """), {"id": facility_id, "n": name})


@pytest.fixture
async def facility_a():
    fac = f"test-fac-a-{uuid.uuid4().hex[:8]}"
    await _seed_facility(fac, "Test Facility A")
    return fac


@pytest.fixture
async def facility_b():
    fac = f"test-fac-b-{uuid.uuid4().hex[:8]}"
    await _seed_facility(fac, "Test Facility B")
    return fac


@pytest.fixture
def token_for():
    def _make(facility_id, role="worker"):
        return issue_token(
            user_id="test-user", username="test-user",
            role=role, facility_id=facility_id,
        )
    return _make


@pytest.fixture(autouse=True)
async def _dispose_engines():
    """Drop engine connections after each test so asyncpg does not reuse a
    connection bound to a closed event loop."""
    yield
    from app.db import app_engine, admin_engine, seed_engine
    await app_engine.dispose()
    await admin_engine.dispose()
    await seed_engine.dispose()
