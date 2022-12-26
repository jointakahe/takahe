import pytest

from activities.models import Post
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
