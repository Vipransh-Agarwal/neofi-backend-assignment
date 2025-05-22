import pytest
from httpx import AsyncClient
from fastapi import status

async def test_register_user(client):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "password" not in data

async def test_register_duplicate_username(client, test_user):
    # First registration
    await client.post("/api/auth/register", json=test_user)
    
    # Attempt duplicate registration
    response = await client.post("/api/auth/register", json=test_user)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

async def test_login_success(client, test_user):
    # Register user first
    await client.post("/api/auth/register", json=test_user)
    
    # Attempt login
    response = await client.post(
        "/api/auth/login",
        json={
            "username": test_user["username"],
            "password": test_user["password"]
        }
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in data

async def test_login_invalid_credentials(client):
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "nonexistent",
            "password": "wrong"
        }
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_refresh_token(client, test_user):
    # Register and login to get tokens
    await client.post("/api/auth/register", json=test_user)
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": test_user["username"],
            "password": test_user["password"]
        }
    )
    refresh_token = login_response.json()["refresh_token"]
    
    # Use refresh token to get new access token
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

async def test_protected_route_with_token(client, test_user_token):
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK

async def test_protected_route_without_token(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
