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
