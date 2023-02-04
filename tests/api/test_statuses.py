import pytest

from activities.models import Post


@pytest.mark.django_db
def test_post_status(api_token, identity, client):
    response = client.post(
        "/api/v1/statuses",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
        data={
            "status": "Hello, world!",
            "visibility": "unlisted",
        },
    ).json()
    assert response["content"] == "<p>Hello, world!</p>"
    assert response["visibility"] == "unlisted"


@pytest.mark.django_db
def test_mention_format(api_token, identity, remote_identity, client):
    """
    Ensures mentions work, and only have one link around them.
    """
    # Make a local post and check it
    response = client.post(
        "/api/v1/statuses",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
        data={
            "status": "Hello, @test!",
            "visibility": "unlisted",
        },
    ).json()
    assert (
        response["content"]
        == '<p>Hello, <a href="https://example.com/@test/">@test</a>!</p>'
    )
    assert response["visibility"] == "unlisted"

    # Make a remote post and check it
    post = Post.objects.create(
        local=False,
        author=remote_identity,
        content='<p>Hey <a href="https://example.com/@test/" class="u-url mention" rel="nofollow">@test</a></p>',
        object_uri="https://remote.test/status/12345",
    )
    post.mentions.add(identity)
    response = client.get(
        f"/api/v1/statuses/{post.id}",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
    ).json()
    assert (
        response["text"] == '<p>Hey <a href="https://example.com/@test/">@test</a></p>'
    )
