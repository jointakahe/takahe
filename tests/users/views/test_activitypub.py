import pytest


@pytest.mark.django_db
def test_webfinger_actor(client, identity):
    """
    Ensures the webfinger and actor URLs are working properly
    """
    identity.generate_keypair()
    # Fetch their webfinger
    data = client.get("/.well-known/webfinger?resource=acct:test@example.com").json()
    assert data["subject"] == "acct:test@example.com"
    assert data["aliases"][0] == "https://example.com/@test/"
    # Fetch their actor
    data = client.get("/@test@example.com/", HTTP_ACCEPT="application/ld+json").json()
    assert data["id"] == "https://example.com/@test@example.com/"


@pytest.mark.django_db
def test_webfinger_system_actor(client):
    """
    Ensures the webfinger and actor URLs are working properly for system actor
    """
    # Fetch their webfinger
    data = client.get(
        "/.well-known/webfinger?resource=acct:__system__@example.com"
    ).json()
    assert data["subject"] == "acct:__system__@example.com"
    assert data["aliases"][0] == "https://example.com/about/"
    # Fetch their actor
    data = client.get("/actor/", HTTP_ACCEPT="application/ld+json").json()
    assert data["id"] == "https://example.com/actor/"
    assert data["inbox"] == "https://example.com/actor/inbox/"
