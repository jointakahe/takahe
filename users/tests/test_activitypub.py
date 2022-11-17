import pytest

from users.models import Domain, Identity, User


@pytest.mark.django_db
def test_webfinger_actor(client):
    """
    Ensures the webfinger and actor URLs are working properly
    """
    # Make a user
    user = User.objects.create(email="test@example.com")
    # Make a domain
    domain = Domain.objects.create(domain="example.com", local=True)
    domain.users.add(user)
    # Make an identity for them
    identity = Identity.objects.create(
        actor_uri="https://example.com/@test@example.com/actor/",
        username="test",
        domain=domain,
        name="Test User",
        local=True,
    )
    identity.generate_keypair()
    # Fetch their webfinger
    data = client.get("/.well-known/webfinger?resource=acct:test@example.com").json()
    assert data["subject"] == "acct:test@example.com"
    assert data["aliases"][0] == "https://example.com/@test/"
    # Fetch their actor
    data = client.get("/@test@example.com/actor/").json()
    assert data["id"] == "https://example.com/@test@example.com/actor/"
