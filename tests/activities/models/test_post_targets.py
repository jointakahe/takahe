import pytest
from asgiref.sync import async_to_sync

from activities.models import Post
from users.models import Follow


@pytest.mark.django_db
def test_post_targets_simple(identity, other_identity, remote_identity):
    """
    Tests that a simple top level post returns the correct targets.
    """
    # Test a post with no mentions targets author
    post = Post.objects.create(
        content="<p>Hello</p>",
        author=identity,
        local=True,
    )
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity}

    # Test remote reply targets original post author
    Post.objects.create(
        content="<p>Reply</p>",
        author=remote_identity,
        local=False,
        in_reply_to=post.absolute_object_uri(),
    )
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity}

    # Test a post with local and remote mentions
    post = Post.objects.create(
        content="<p>Hello @test and @other</p>",
        author=identity,
        local=True,
    )
    # Mentions are targeted
    post.mentions.add(remote_identity)
    post.mentions.add(other_identity)
    targets = async_to_sync(post.aget_targets)()
    # Targets everyone
    assert targets == {identity, other_identity, remote_identity}

    # Test remote post with mentions
    post.local = False
    post.save()
    targets = async_to_sync(post.aget_targets)()
    # Only targets locals who are mentioned
    assert targets == {other_identity}


@pytest.mark.django_db
def test_post_local_only(identity, other_identity, remote_identity):
    """
    Tests that a simple top level post returns the correct targets.
    """
    # Test a short username (remote)
    post = Post.objects.create(
        content="<p>Hello @test and @other</p>",
        author=identity,
        local=True,
        visibility=Post.Visibilities.local_only,
    )
    post.mentions.add(remote_identity)
    post.mentions.add(other_identity)

    # Remote mention is not targeted
    post.mentions.add(remote_identity)
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity, other_identity}


@pytest.mark.django_db
def test_post_followers(identity, other_identity, remote_identity):

    Follow.objects.create(source=other_identity, target=identity)
    Follow.objects.create(source=remote_identity, target=identity)

    # Test Public post w/o mentions targets self and followers
    post = Post.objects.create(
        content="<p>Hello</p>",
        author=identity,
        local=True,
        visibility=Post.Visibilities.public,
    )
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity, other_identity, remote_identity}

    # Remote post only targets local followers, not the author
    post.local = False
    post.save()
    targets = async_to_sync(post.aget_targets)()
    assert targets == {other_identity}

    # Local Only post only targets local followers
    post.local = True
    post.visibility = Post.Visibilities.local_only
    post.save()
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity, other_identity}

    # Mentioned posts do not target unmentioned followers
    post.visibility = Post.Visibilities.mentioned
    post.save()
    targets = async_to_sync(post.aget_targets)()
    assert targets == {identity}
