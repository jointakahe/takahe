import pytest

from activities.models import Post, PostInteraction
from activities.services import PostService
from users.models import Identity


@pytest.mark.django_db
def test_post_context(identity: Identity, config_system):
    """
    Tests that post context fetching works correctly
    """
    post1 = Post.create_local(
        author=identity,
        content="<p>first</p>",
        visibility=Post.Visibilities.public,
    )
    post2 = Post.create_local(
        author=identity,
        content="<p>second</p>",
        visibility=Post.Visibilities.public,
        reply_to=post1,
    )
    post3 = Post.create_local(
        author=identity,
        content="<p>third</p>",
        visibility=Post.Visibilities.public,
        reply_to=post2,
    )
    # Test the view from the start of thread
    ancestors, descendants = PostService(post1).context(None)
    assert ancestors == []
    assert descendants == [post2, post3]
    # Test the view from the end of thread
    ancestors, descendants = PostService(post3).context(None)
    assert ancestors == [post2, post1]
    assert descendants == []


@pytest.mark.django_db
def test_pin_as(identity: Identity, identity2: Identity, config_system):
    post = Post.create_local(
        author=identity,
        content="Hello world",
    )
    mentioned_post = Post.create_local(
        author=identity,
        content="mentioned-only post",
        visibility=Post.Visibilities.mentioned,
    )

    service = PostService(post)
    assert (
        PostInteraction.objects.filter(
            identity=identity, type=PostInteraction.Types.pin
        ).count()
        == 0
    )

    service.pin_as(identity)
    assert (
        PostInteraction.objects.filter(
            identity=identity, post=post, type=PostInteraction.Types.pin
        ).count()
        == 1
    )

    # pinning same post is a no-op
    service.pin_as(identity)
    assert (
        PostInteraction.objects.filter(
            identity=identity, post=post, type=PostInteraction.Types.pin
        ).count()
        == 1
    )

    # Identity can only pin their own posts
    with pytest.raises(ValueError):
        service.pin_as(identity2)
    assert (
        PostInteraction.objects.filter(
            identity=identity2, post=post, type=PostInteraction.Types.pin
        ).count()
        == 0
    )

    # Cannot pin a post with mentioned-only visibility
    with pytest.raises(ValueError):
        PostService(mentioned_post).pin_as(identity)
    assert (
        PostInteraction.objects.filter(
            identity=identity2, post=mentioned_post, type=PostInteraction.Types.pin
        ).count()
        == 0
    )

    # Can only pin max 5 posts
    for i in range(5):
        new_post = Post.create_local(
            author=identity2,
            content=f"post {i}",
        )
        PostService(new_post).pin_as(identity2)
    post = Post.create_local(author=identity2, content="post 6")
    with pytest.raises(ValueError):
        PostService(post).pin_as(identity2)
    assert (
        PostInteraction.objects.filter(
            identity=identity2, type=PostInteraction.Types.pin
        ).count()
        == 5
    )
