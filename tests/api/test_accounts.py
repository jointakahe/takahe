import pytest


@pytest.mark.django_db
def test_verify_credentials(api_token, identity, client):
    response = client.get(
        "/api/v1/accounts/verify_credentials",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
    ).json()
    assert response["id"] == str(identity.pk)
    assert response["username"] == identity.username


@pytest.mark.django_db
def test_account_search(api_token, identity, client):
    response = client.get(
        "/api/v1/accounts/search?q=test",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
    ).json()
    assert response[0]["id"] == str(identity.pk)
    assert response[0]["username"] == identity.username
