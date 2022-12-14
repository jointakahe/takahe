import pytest


@pytest.mark.django_db
def test_post_status(api_token, identity, client):
    response = client.post(
        "/api/v1/statuses",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
        data={
            "status": "Hello, world!",
            "visibility": "unlisted",
        },
    ).json()
    assert response["content"] == "<p>Hello, world!</p>"
    assert response["visibility"] == "unlisted"
