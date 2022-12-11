import pytest


@pytest.mark.django_db
def test_instance(api_token, client):
    response = client.get(
        "/api/v1/instance",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
    ).json()
    assert response["uri"] == "example.com"
