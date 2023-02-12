from datetime import timedelta

import pytest
from django.utils import timezone

from activities.models import Post
from core.ld import format_ld_date


@pytest.mark.django_db
def test_get_poll(api_token, client):
    response = client.post(
        "/api/v1/statuses",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
        data={
            "status": "Hello, world!",
            "poll": {
                "options": ["Option 1", "Option 2"],
                "expires_in": 300,
            },
        },
    ).json()

    id = response["id"]

    response = client.get(
        f"/api/v1/polls/{id}",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
    ).json()

    assert response["id"] == id
    assert response["voted"]


@pytest.mark.django_db
def test_vote_poll(api_token, identity2, client):
    post = Post.create_local(
        author=identity2,
        content="<p>Test Question</p>",
        question={
            "type": "Question",
            "mode": "oneOf",
            "options": [
                {"name": "Option 1", "type": "Note", "votes": 0},
                {"name": "Option 2", "type": "Note", "votes": 0},
            ],
            "voter_count": 0,
            "end_time": format_ld_date(timezone.now() + timedelta(1)),
        },
    )

    response = client.post(
        f"/api/v1/polls/{post.id}/votes",
        HTTP_AUTHORIZATION=f"Bearer {api_token.token}",
        HTTP_ACCEPT="application/json",
        content_type="application/json",
        data={
            "choices": [0],
        },
    ).json()

    assert response["id"] == str(post.id)
    assert response["voted"]
    assert response["votes_count"] == 1
    assert response["own_votes"] == [0]
