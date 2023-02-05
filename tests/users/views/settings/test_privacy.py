import pytest
from pytest_django.asserts import assertContains, assertNotContains

from core.models.config import Config
from users.models import Follow


@pytest.mark.django_db
def test_stats(client, identity, other_identity):
    """
    Tests that follow stats are visible
    """
    Follow.objects.create(source=other_identity, target=identity)
    Config.set_identity(identity, "visible_follows", True)
    response = client.get(identity.urls.view)
    assertContains(response, "<strong>1</strong> follower", status_code=200)


@pytest.mark.django_db
def test_visible_follows_disabled(client, identity):
    """
    Tests that disabling visible follows hides it from profile
    """
    Config.set_identity(identity, "visible_follows", True)
    response = client.get(identity.urls.view)
    assertContains(response, "follower", status_code=200)
    Config.set_identity(identity, "visible_follows", False)
    response = client.get(identity.urls.view)
    assertNotContains(response, "follower", status_code=200)
