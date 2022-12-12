import pytest
from pytest_django.asserts import assertContains, assertNotContains

from users.models import Follow


@pytest.mark.django_db
def test_stats(client, identity, other_identity):
    """
    Tests that follow stats are visible
    """
    Follow.objects.create(source=other_identity, target=identity)
    response = client.get(identity.urls.view)
    assertContains(response, "<strong>1</strong> followers", status_code=200)


@pytest.mark.django_db
def test_visible_follows_disabled(client, identity):
    """
    Tests that disabling visible follows hides it from profile
    """
    identity.visible_follows = False
    identity.save()
    response = client.get(identity.urls.view)
    assertNotContains(response, '<div class="stats">', status_code=200)
