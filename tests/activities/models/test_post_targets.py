import pytest
from asgiref.sync import async_to_sync

from activities.models import Post
from users.models import Domain, Follow, Identity


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
def test_post_targets_shared(identity, other_identity):
    """
    Tests that remote identities with the same shared inbox only get one target.
    """
    # Create a pair of remote identities that share an inbox URI
    domain = Domain.objects.create(domain="remote.test", local=False, state="updated")
    remote1 = Identity.objects.create(
        actor_uri="https://remote.test/test1/",
        inbox_uri="https://remote.test/@test1/inbox/",
        shared_inbox_uri="https://remote.test/inbox/",
        profile_uri="https://remote.test/@test1/",
        username="test1",
        domain=domain,
        name="Test1",
        local=False,
        state="updated",
    )
    remote2 = Identity.objects.create(
        actor_uri="https://remote.test/test2/",
        inbox_uri="https://remote.test/@test2/inbox/",
        shared_inbox_uri="https://remote.test/inbox/",
        profile_uri="https://remote.test/@test2/",
        username="test2",
        domain=domain,
        name="Test2",
        local=False,
        state="updated",
    )

    # Make a post mentioning one local and two remote identities
    post = Post.objects.create(
        content="<p>Test</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(other_identity)
    post.mentions.add(remote1)
    post.mentions.add(remote2)
    targets = async_to_sync(post.aget_targets)()

    # We should only have one of remote1 or remote2 in there as they share a
    # shared inbox URI
    assert (targets == {identity, other_identity, remote1}) or (
        targets
        == {
            identity,
            other_identity,
            remote2,
        }
    )


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
