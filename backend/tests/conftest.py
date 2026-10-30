import os, uuid
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL","postgresql+asyncpg://sentinel:change-me@localhost:6432/sentinel")
os.environ.setdefault("DATABASE_URL_ADMIN","postgresql+asyncpg://sentinel_admin:change-me@localhost:6432/sentinel")
os.environ.setdefault("JWT_SECRET","test-secret")
os.environ.setdefault("WORKER_ID_PEPPER","test-pepper")

from app.bff.app import app as bff_app
from app.security import issue_token


@pytest.fixture
async def client():
    t = ASGITransport(app=bff_app)
    async with AsyncClient(transport=t, base_url="http://bff") as c:
        yield c


@pytest.fixture
def facility_a(): return f"fac-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def facility_b(): return f"fac-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def token_for():
    def _make(facility_id, role="worker"):
        return issue_token(sub="test-user", role=role, facility_id=facility_id)
    return _make


@pytest.fixture(autouse=True)
async def _dispose_engines():
    """Drop engine connections after each test so asyncpg does not reuse a
    connection bound to a closed event loop."""
    yield
    from app.db import app_engine, admin_engine
    await app_engine.dispose()
    await admin_engine.dispose()
