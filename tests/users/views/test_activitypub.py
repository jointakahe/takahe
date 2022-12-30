import pytest


@pytest.mark.django_db
def test_webfinger_actor(client, identity):
    """
    Ensures the webfinger and actor URLs are working properly
    """
    identity.generate_keypair()
    # Fetch their webfinger
    response = client.get("/.well-known/webfinger?resource=acct:test@example.com")
    assert response.headers["content-type"] == "application/jrd+json"
    data = response.json()
    assert data["subject"] == "acct:test@example.com"
    assert data["aliases"][0] == "https://example.com/@test/"
    # Fetch their actor
    data = client.get("/@test@example.com/", HTTP_ACCEPT="application/ld+json").json()
    assert data["id"] == "https://example.com/@test@example.com/"
    assert data["endpoints"]["sharedInbox"] == "https://example.com/inbox/"


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
    assert data["endpoints"]["sharedInbox"] == "https://example.com/inbox/"


@pytest.mark.django_db
def test_delete_actor(client, identity):
    data = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "actor": "https://mastodon.social/users/fakec8b6984105c8f15070a2",
        "id": "https://mastodon.social/users/fakec8b6984105c8f15070a2#delete",
        "object": "https://mastodon.social/users/fakec8b6984105c8f15070a2",
        "signature": {
            "created": "2022-12-06T03:54:28Z",
            "creator": "https://mastodon.social/users/fakec8b6984105c8f15070a2#main-key",
            "signatureValue": "This value doesn't matter",
            "type": "RsaSignature2017",
        },
        "to": ["https://www.w3.org/ns/activitystreams#Public"],
        "type": "Delete",
    }
    resp = client.post(
        identity.inbox_uri, data=data, content_type="application/activity+json"
    )
    assert resp.status_code == 202
