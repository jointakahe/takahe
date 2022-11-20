import pytest

from core.models import Config
from users.models import Domain, Identity, User
from users.views.identity import CreateIdentity


@pytest.mark.django_db
def test_create_identity_form(client):
    """ """
    # Make a user
    user = User.objects.create(email="test@example.com")
    admin = User.objects.create(email="admin@example.com", admin=True)
    # Make a domain
    domain = Domain.objects.create(domain="example.com", local=True)
    domain.users.add(user)
    domain.users.add(admin)

    # Test identity_min_length
    data = {
        "username": "a",
        "domain": domain.domain,
        "name": "The User",
    }

    form = CreateIdentity.form_class(user=user, data=data)
    assert not form.is_valid()
    assert "username" in form.errors
    assert "value has at least" in form.errors["username"][0]

    form = CreateIdentity.form_class(user=admin, data=data)
    assert form.errors == {}

    # Test restricted_usernames
    data = {
        "username": "@root",
        "domain": domain.domain,
        "name": "The User",
    }

    form = CreateIdentity.form_class(user=user, data=data)
    assert not form.is_valid()
    assert "username" in form.errors
    assert "restricted to administrators" in form.errors["username"][0]

    form = CreateIdentity.form_class(user=admin, data=data)
    assert form.errors == {}

    # Test valid chars
    data = {
        "username": "@someval!!!!",
        "domain": domain.domain,
        "name": "The User",
    }

    for u in (user, admin):
        form = CreateIdentity.form_class(user=u, data=data)
        assert not form.is_valid()
        assert "username" in form.errors
        assert form.errors["username"][0].startswith("Only the letters")


@pytest.mark.django_db
def test_identity_max_per_user(client):
    """
    Ensures the webfinger and actor URLs are working properly
    """
    # Make a user
    user = User.objects.create(email="test@example.com")
    # Make a domain
    domain = Domain.objects.create(domain="example.com", local=True)
    domain.users.add(user)
    # Make an identity for them
    for i in range(Config.system.identity_max_per_user):
        identity = Identity.objects.create(
            actor_uri=f"https://example.com/@test{i}@example.com/actor/",
            username=f"test{i}",
            domain=domain,
            name=f"Test User{i}",
            local=True,
        )
        identity.users.add(user)

    data = {
        "username": "toomany",
        "domain": domain.domain,
        "name": "Too Many",
    }
    form = CreateIdentity.form_class(user=user, data=data)
    assert form.errors["__all__"][0].startswith("You are not allowed more than")

    user.admin = True
    form = CreateIdentity.form_class(user=user, data=data)
    assert form.is_valid()
