import pytest
from django.test.client import Client
from pytest_django.asserts import assertContains

from users.models import Identity


@pytest.mark.django_db
def test_rate_limit(identity: Identity, client_with_user: Client):
    """
    Tests that the posting rate limit comes into force
    """
    # First post should go through
    assert identity.posts.count() == 0
    response = client_with_user.post(
        f"/@{identity.handle}/compose/", data={"text": "post 1", "visibility": "0"}
    )
    assert response.status_code == 302
    assert identity.posts.count() == 1
    # Second should not
    response = client_with_user.post(
        f"/@{identity.handle}/compose/", data={"text": "post 2", "visibility": "0"}
    )
    assertContains(response, "You must wait at least", status_code=200)
    assert identity.posts.count() == 1
