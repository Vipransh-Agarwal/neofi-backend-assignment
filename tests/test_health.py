import pytest
from fastapi import status

async def test_basic_health(client):
    response = await client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"

async def test_detailed_health(client):
    response = await client.get("/api/health/detailed")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "api" in data["components"]
    assert "database" in data["components"]

async def test_protected_health(client, test_user_token):
    response = await client.get(
        "/api/health/protected",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "metrics" in data
    assert "cpu_percent" in data["metrics"]
    assert "memory_percent" in data["metrics"]
    assert "disk_usage" in data["metrics"]

async def test_protected_health_unauthorized(client):
    response = await client.get("/api/health/protected")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
