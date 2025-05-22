import pytest
from datetime import datetime, timedelta
from fastapi import status

@pytest.fixture
def test_event():
    return {
        "title": "Test Event",
        "description": "Test Description",
        "start_datetime": (datetime.now() + timedelta(days=1)).isoformat(),
        "end_datetime": (datetime.now() + timedelta(days=1, hours=2)).isoformat(),
        "recurrence_rule": None,
        "recurrence_end": None
    }

async def test_create_event(client, test_user_token, test_event):
    response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["title"] == test_event["title"]
    assert data["description"] == test_event["description"]

async def test_create_recurring_event(client, test_user_token, test_event):
    test_event["recurrence_rule"] = "FREQ=WEEKLY;COUNT=4"
    test_event["recurrence_end"] = (datetime.now() + timedelta(days=28)).isoformat()
    
    response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["recurrence_rule"] == test_event["recurrence_rule"]

async def test_get_event(client, test_user_token, test_event):
    # Create event first
    create_response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    event_id = create_response.json()["id"]
    
    # Get the created event
    response = await client.get(
        f"/api/events/{event_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == event_id
    assert data["title"] == test_event["title"]

async def test_update_event(client, test_user_token, test_event):
    # Create event first
    create_response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    event_id = create_response.json()["id"]
    
    # Update the event
    update_data = {"title": "Updated Title"}
    response = await client.put(
        f"/api/events/{event_id}",
        json=update_data,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "Updated Title"

async def test_delete_event(client, test_user_token, test_event):
    # Create event first
    create_response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    event_id = create_response.json()["id"]
    
    # Delete the event
    response = await client.delete(
        f"/api/events/{event_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify event is deleted
    get_response = await client.get(
        f"/api/events/{event_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_response.status_code == status.HTTP_404_NOT_FOUND

async def test_list_events(client, test_user_token, test_event):
    # Create multiple events
    for i in range(3):
        test_event["title"] = f"Test Event {i}"
        await client.post(
            "/api/events",
            json=test_event,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
    
    response = await client.get(
        "/api/events",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 3

async def test_event_conflict_detection(client, test_user_token, test_event):
    # Create first event
    await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    # Try to create overlapping event
    response = await client.post(
        "/api/events",
        json=test_event,  # Same time slot
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
