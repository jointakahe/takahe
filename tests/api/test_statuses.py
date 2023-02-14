import pytest

from activities.models import Post


@pytest.mark.django_db
def test_post_status(api_client):
    """
    Tests posting, editing and deleting a status
    """
    # Post new one
    response = api_client.post(
        "/api/v1/statuses",
        content_type="application/json",
        data={
            "status": "Hello, world!",
            "visibility": "unlisted",
        },
    ).json()
    assert response["content"] == "<p>Hello, world!</p>"
    assert response["visibility"] == "unlisted"
    status_id = response["id"]
    # Retrieve "source" version an edit would use
    response = api_client.get(f"/api/v1/statuses/{status_id}/source").json()
    assert response["text"] == "Hello, world!"
    # Post an edit
    response = api_client.put(
        f"/api/v1/statuses/{status_id}",
        content_type="application/json",
        data={
            "status": "Hello, world! Again!",
        },
    ).json()
    # Check it stuck
    response = api_client.get(f"/api/v1/statuses/{status_id}").json()
    assert response["content"] == "<p>Hello, world! Again!</p>"
    # Delete it
    response = api_client.delete(f"/api/v1/statuses/{status_id}")
    assert response.status_code == 200
    # Check it's gone
    response = api_client.get(f"/api/v1/statuses/{status_id}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_mention_format(api_client, identity, remote_identity):
    """
    Ensures mentions work, and only have one link around them.
    """
    # Make a local post and check it
    response = api_client.post(
        "/api/v1/statuses",
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
    response = api_client.get(
        f"/api/v1/statuses/{post.id}",
    ).json()
    assert (
        response["text"] == '<p>Hey <a href="https://example.com/@test/">@test</a></p>'
    )
