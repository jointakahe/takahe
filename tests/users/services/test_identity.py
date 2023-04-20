import pytest

from activities.models import Post
from users.models import Identity
from users.services import IdentityService


@pytest.mark.django_db
def test_pin_post(identity: Identity, identity2: Identity, config_system):
    post = Post.create_local(
        author=identity,
        content="Hello world",
    )
    mentioned_post = Post.create_local(
        author=identity,
        content="mentioned-only post",
        visibility=Post.Visibilities.mentioned,
    )

    service = IdentityService(identity)
    assert identity.pinned is None

    service.pin_post(post)
    assert identity.pinned == [post.object_uri]

    # pinning same post should be a no-op
    service.pin_post(post)
    assert identity.pinned == [post.object_uri]

    # Identity can only pin their own posts
    with pytest.raises(ValueError):
        IdentityService(identity2).pin_post(post)

    # Cannot pin a post with mentioned-only visibility
    with pytest.raises(ValueError):
        service.pin_post(mentioned_post)

    # Can only pin max 5 posts
    identity.pinned = [
        "http://instance/user/post-1",
        "http://instance/user/post-2",
        "http://instance/user/post-3",
        "http://instance/user/post-4",
        "http://instance/user/post-5",
    ]
    with pytest.raises(ValueError):
        service.pin_post(post)


@pytest.mark.django_db
def test_unpin_post(identity: Identity, config_system):
    post = Post.create_local(
        author=identity,
        content="Hello world",
    )
    other_post = Post.create_local(
        author=identity,
        content="Other post",
    )

    service = IdentityService(identity)
    assert identity.pinned is None

    service.pin_post(post)
    assert identity.pinned == [post.object_uri]
    service.unpin_post(post)
    assert identity.pinned == []

    # unpinning unpinned post results in no-op
    service.pin_post(post)
    assert identity.pinned == [post.object_uri]
    service.unpin_post(other_post)
    assert identity.pinned == [post.object_uri]
