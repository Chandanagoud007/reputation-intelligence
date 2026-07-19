"""
Tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, test_tenant_data):
    response = await client.post("/api/v1/auth/register", json=test_tenant_data)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_slug(client: AsyncClient, test_tenant_data):
    # First registration
    await client.post("/api/v1/auth/register", json=test_tenant_data)
    # Second registration with same slug
    response = await client.post("/api/v1/auth/register", json=test_tenant_data)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_tenant_data, test_login_data):
    # Register first
    await client.post("/api/v1/auth/register", json=test_tenant_data)
    # Then login
    response = await client.post("/api/v1/auth/login", json=test_login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_tenant_data):
    await client.post("/api/v1/auth/register", json=test_tenant_data)
    response = await client.post("/api/v1/auth/login", json={
        "email": test_tenant_data["email"],
        "password": "WrongPassword!",
        "tenant_slug": test_tenant_data["tenant_slug"]
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
