"""
Pytest configuration and shared fixtures.
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

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
    return {
        "tenant_name": "Test Corp",
        "tenant_slug": "test-corp",
        "email": "admin@testcorp.com",
        "password": "TestPass123!",
        "full_name": "Test Admin"
    }


@pytest.fixture
def test_login_data():
    return {
        "email": "admin@testcorp.com",
        "password": "TestPass123!",
        "tenant_slug": "test-corp"
    }
