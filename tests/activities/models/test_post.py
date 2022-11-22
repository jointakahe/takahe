import pytest
from pytest_httpx import HTTPXMock

from activities.models import Post


@pytest.mark.django_db
def test_fetch_post(httpx_mock: HTTPXMock):
    """
    Tests that a post we don't have locally can be fetched by by_object_uri
    """
    httpx_mock.add_response(
        url="https://example.com/test-post",
        json={
            "@context": [
                "https://www.w3.org/ns/activitystreams",
            ],
            "id": "https://example.com/test-post",
            "type": "Note",
            "published": "2022-11-13T23:20:16Z",
            "url": "https://example.com/test-post",
            "attributedTo": "https://example.com/test-actor",
            "content": "BEEEEEES",
        },
    )
    # Fetch with a HTTP access
    post = Post.by_object_uri("https://example.com/test-post", fetch=True)
    assert post.content == "BEEEEEES"
    assert post.author.actor_uri == "https://example.com/test-actor"
    # Fetch again with a DB hit
    assert Post.by_object_uri("https://example.com/test-post").id == post.id


@pytest.mark.django_db
def test_linkify_mentions_remote(identity, remote_identity):
    """
    Tests that we can linkify post mentions properly for remote use
    """
    # Test a short username (remote)
    post = Post.objects.create(
        content="<p>Hello @test</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_remote()
        == '<p>Hello <a href="https://remote.test/@test/">@test</a></p>'
    )
    # Test a full username (local)
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(identity)
    assert (
        post.safe_content_remote()
        == '<p><a href="https://example.com/@test/">@test@example.com</a>, welcome!</p>'
    )
    # Test that they don't get touched without a mention
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    assert post.safe_content_remote() == "<p>@test@example.com, welcome!</p>"


@pytest.mark.django_db
def test_linkify_mentions_local(identity, remote_identity):
    """
    Tests that we can linkify post mentions properly for local use
    """
    # Test a short username (remote)
    post = Post.objects.create(
        content="<p>Hello @test</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_local()
        == '<p>Hello <a href="/@test@remote.test/">@test</a></p>'
    )
    # Test a full username (local)
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(identity)
    assert (
        post.safe_content_local()
        == '<p><a href="/@test@example.com/">@test@example.com</a>, welcome!</p>'
    )
    # Test that they don't get touched without a mention
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    assert post.safe_content_local() == "<p>@test@example.com, welcome!</p>"
