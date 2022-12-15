import pytest
from django.test.client import Client
from pytest_django.asserts import assertContains

from activities.models import Post
from core.models import Config
from users.models import Identity


@pytest.mark.django_db
def test_content_warning_text(
    client_with_identity: Client,
    config_system: Config.SystemOptions,
):
    """
    Tests that changing the content warning name works
    """
    config_system.content_warning_text = "Content Summary"
    response = client_with_identity.get("/compose/")
    assertContains(response, 'placeholder="Content Summary"', status_code=200)
    assertContains(
        response, "<label for='id_content_warning'>Content Summary</label>", html=True
    )


@pytest.mark.django_db
def test_post_edit_security(client_with_identity: Client, other_identity: Identity):
    """
    Tests that you can't edit other users' posts with URL fiddling
    """
    other_post = Post.objects.create(
        content="<p>OTHER POST!</p>",
        author=other_identity,
        local=True,
        visibility=Post.Visibilities.public,
    )
    response = client_with_identity.get(other_post.urls.action_edit)
    assert response.status_code == 403


@pytest.mark.django_db
def test_rate_limit(identity: Identity, client_with_identity: Client):
    """
    Tests that the posting rate limit comes into force
    """
    # First post should go through
    assert identity.posts.count() == 0
    response = client_with_identity.post(
        "/compose/", data={"text": "post 1", "visibility": "0"}
    )
    assert response.status_code == 302
    assert identity.posts.count() == 1
    # Second should not
    response = client_with_identity.post(
        "/compose/", data={"text": "post 2", "visibility": "0"}
    )
    assertContains(response, "You must wait at least", status_code=200)
    assert identity.posts.count() == 1
