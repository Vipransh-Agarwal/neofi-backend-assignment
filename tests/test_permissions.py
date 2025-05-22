import pytest
from fastapi import status

@pytest.fixture
async def test_event_id(client, test_user_token, test_event):
    response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    return response.json()["id"]

@pytest.fixture
async def second_user(client):
    user_data = {
        "username": "seconduser",
        "email": "second@example.com",
        "password": "testpass123"
    }
    response = await client.post("/api/auth/register", json=user_data)
    return response.json()

async def test_share_event(client, test_user_token, test_event_id, second_user):
    response = await client.post(
        f"/api/events/{test_event_id}/share",
        json={
            "user_id": second_user["id"],
            "can_edit": True
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

async def test_list_permissions(client, test_user_token, test_event_id, second_user):
    # Share event first
    await client.post(
        f"/api/events/{test_event_id}/share",
        json={
            "user_id": second_user["id"],
            "can_edit": True
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    # List permissions
    response = await client.get(
        f"/api/events/{test_event_id}/permissions",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["username"] == second_user["username"]
    assert data[0]["can_edit"] == True

async def test_update_permission(client, test_user_token, test_event_id, second_user):
    # Share event first
    await client.post(
        f"/api/events/{test_event_id}/share",
        json={
            "user_id": second_user["id"],
            "can_edit": True
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    # Update permission to read-only
    response = await client.put(
        f"/api/events/{test_event_id}/permissions/{second_user['id']}",
        json={"can_edit": False},
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["can_edit"] == False

async def test_revoke_permission(client, test_user_token, test_event_id, second_user):
    # Share event first
    await client.post(
        f"/api/events/{test_event_id}/share",
        json={
            "user_id": second_user["id"],
            "can_edit": True
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    # Revoke permission
    response = await client.delete(
        f"/api/events/{test_event_id}/permissions/{second_user['id']}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify permission is revoked
    list_response = await client.get(
        f"/api/events/{test_event_id}/permissions",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    data = list_response.json()
    assert len(data) == 0
