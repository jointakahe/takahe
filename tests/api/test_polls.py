from datetime import timedelta

import pytest
from django.utils import timezone

from activities.models import Post
from core.ld import format_ld_date


@pytest.mark.django_db
def test_get_poll(api_client):
    response = api_client.post(
        "/api/v1/statuses",
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

    response = api_client.get(
        f"/api/v1/polls/{id}",
    ).json()

    assert response["id"] == id
    assert response["voted"]


@pytest.mark.django_db
def test_vote_poll(api_client, identity2):
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

    response = api_client.post(
        f"/api/v1/polls/{post.id}/votes",
        content_type="application/json",
        data={
            "choices": [0],
        },
    ).json()

    assert response["id"] == str(post.id)
    assert response["voted"]
    assert response["votes_count"] == 1
    assert response["own_votes"] == [0]
