import pytest


@pytest.mark.django_db
def test_likes_flow(api_client):
    # Add a post
    response = api_client.post(
        "/api/v1/statuses",
        content_type="application/json",
        data={
            "status": "Like test.",
            "visibility": "public",
        },
    ).json()
    assert response["content"] == "<p>Like test.</p>"

    status_id = response["id"]

    # Like it
    response = api_client.post(f"/api/v1/statuses/{status_id}/favourite").json()
    assert response["favourited"] is True

    # Check if it's displaying at likes endpoint
    response = api_client.get("/api/v1/favourites").json()
    assert response[0]["id"] == status_id
