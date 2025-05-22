import pytest
from fastapi import status
from datetime import datetime, timedelta

@pytest.fixture
async def test_event_with_versions(client, test_user_token, test_event):
    # Create initial event
    response = await client.post(
        "/api/events",
        json=test_event,
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    event_id = response.json()["id"]
    
    # Make some updates to create versions
    updates = [
        {"title": "Updated Title 1"},
        {"title": "Updated Title 2"},
        {"description": "Updated Description"}
    ]
    
    for update in updates:
        await client.put(
            f"/api/events/{event_id}",
            json=update,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
    
    return event_id

async def test_list_versions(client, test_user_token, test_event_with_versions):
    response = await client.get(
        f"/api/events/{test_event_with_versions}/history",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    versions = response.json()
    assert len(versions) == 4  # Initial + 3 updates
    assert all("version_number" in v for v in versions)
    assert all("created_at" in v for v in versions)

async def test_get_specific_version(client, test_user_token, test_event_with_versions):
    response = await client.get(
        f"/api/events/{test_event_with_versions}/history/2",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    version = response.json()
    assert version["version_number"] == 2
    assert "snapshot" in version

async def test_get_version_diff(client, test_user_token, test_event_with_versions):
    response = await client.get(
        f"/api/events/{test_event_with_versions}/diff/1/3",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    diff = response.json()
    assert isinstance(diff, list)

async def test_rollback_version(client, test_user_token, test_event_with_versions):
    response = await client.post(
        f"/api/events/{test_event_with_versions}/rollback/1",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "version_number" in data

async def test_changelog(client, test_user_token, test_event_with_versions):
    response = await client.get(
        f"/api/events/{test_event_with_versions}/changelog",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    changelog = response.json()
    assert isinstance(changelog, list)
    assert len(changelog) > 0
    assert all("changed_at" in entry for entry in changelog)

async def test_get_version_at_timestamp(client, test_user_token, test_event_with_versions):
    # Get a timestamp halfway through the updates
    response = await client.get(
        f"/api/events/{test_event_with_versions}/history",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    versions = response.json()
    timestamp = datetime.fromisoformat(versions[2]["created_at"])
    
    response = await client.get(
        f"/api/events/at",
        params={
            "event_id": test_event_with_versions,
            "at": timestamp.isoformat()
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == status.HTTP_200_OK
    version = response.json()
    assert version["version_number"] == 2
