import pytest


@pytest.mark.django_db
def test_verify_credentials(api_client, identity):
    response = api_client.get("/api/v1/accounts/verify_credentials").json()
    assert response["id"] == str(identity.pk)
    assert response["username"] == identity.username


@pytest.mark.django_db
def test_account_search(api_client, identity):
    response = api_client.get("/api/v1/accounts/search?q=test").json()
    assert response[0]["id"] == str(identity.pk)
    assert response[0]["username"] == identity.username
