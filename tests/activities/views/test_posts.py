import pytest
from django.test.client import Client

from activities.models import Post
from users.models import Identity


@pytest.mark.django_db
def test_post_delete_security(client_with_identity: Client, other_identity: Identity):
    """
    Tests that you can't delete other users' posts with URL fiddling
    """
    other_post = Post.objects.create(
        content="<p>OTHER POST!</p>",
        author=other_identity,
        local=True,
        visibility=Post.Visibilities.public,
    )
    response = client_with_identity.get(other_post.urls.action_delete)
    assert response.status_code == 403
