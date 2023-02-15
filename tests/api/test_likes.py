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


@pytest.mark.django_db
def test_unlike(api_client):
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

    # Unlike it
    response = api_client.post(f"/api/v1/statuses/{status_id}/unfavourite").json()
    assert response["favourited"] is False

    # Unliked post should not display at the endpoint
    response = api_client.get("/api/v1/favourites").json()
    assert len(response) == 0
