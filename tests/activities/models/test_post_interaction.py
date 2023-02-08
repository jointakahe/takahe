import pytest

from activities.models import Post, PostInteraction
from users.models import Identity


@pytest.mark.django_db
def test_vote_in_expired_question(
    identity: Identity, remote_identity: Identity, config_system
):
    post = Post.create_local(
        author=identity,
        content="<p>Test Question</p>",
        question={
            "type": "Question",
            "mode": "oneOf",
            "options": [
                {"name": "Option 1", "type": "Note", "votes": 10},
                {"name": "Option 2", "type": "Note", "votes": 20},
            ],
            "voter_count": 30,
            "end_time": "2022-01-01T23:04:45+00:00",
        },
    )

    with pytest.raises(PostInteraction.DoesNotExist) as ex:
        PostInteraction.by_ap(
            data={
                "id": "https://remote.test/test-actor#votes/389574/activity",
                "to": "https://example.com/@test@example.com/",
                "type": "Create",
                "actor": "https://remote.test/test-actor/",
                "object": {
                    "id": "https://remote.test/users/test-actor#votes/1",
                    "to": "https://example.com/@test@example.com/",
                    "name": "Option 1",
                    "type": "Note",
                    "inReplyTo": post.object_uri,
                    "attributedTo": "https://remote.test/test-actor/",
                },
                "@context": [
                    "https://www.w3.org/ns/activitystreams",
                    {
                        "toot": "http://joinmastodon.org/ns#",
                        "Emoji": "toot:Emoji",
                        "Public": "as:Public",
                        "Hashtag": "as:Hashtag",
                        "votersCount": "toot:votersCount",
                    },
                    "https://w3id.org/security/v1",
                ],
            },
            create=True,
        )
        assert "Cannot create a vote to the expired question" in str(ex)
