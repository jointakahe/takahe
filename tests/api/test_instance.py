import pytest


@pytest.mark.django_db
def test_instance(api_client):
    response = api_client.get("/api/v1/instance").json()
    assert response["uri"] == "example.com"
