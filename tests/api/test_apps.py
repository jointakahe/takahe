import pytest


@pytest.mark.django_db
def test_create(api_client):
    """
    Tests creating an app with mixed query/body params (some clients do this)
    """
    response = api_client.post("/api/v1/apps?client_name=test", {"redirect_uris": ""})
    assert response.status_code == 200
    assert response.json()["name"] == "test"
