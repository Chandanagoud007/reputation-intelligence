"""
Pytest configuration and shared fixtures.
"""
import asyncio
import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from app.models.tenant import Tenant  # noqa
from app.models.brand import Brand  # noqa
from app.models.region import Region  # noqa
from app.models.location import Location  # noqa
from app.models.user import User  # noqa
from app.models.connector import Connector  # noqa
from app.models.alert_rule import AlertRule  # noqa

from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def test_tenant_data():
    suffix = uuid.uuid4().hex[:8]
    return {
        "tenant_name": "Test Corp",
        "tenant_slug": f"test-corp-{suffix}",
        "email": f"admin-{suffix}@testcorp.com",
        "password": "TestPass123!",
        "full_name": "Test Admin"
    }


@pytest.fixture
def test_login_data(test_tenant_data):
    return {
        "email": test_tenant_data["email"],
        "password": "TestPass123!",
        "tenant_slug": test_tenant_data["tenant_slug"]
    }
