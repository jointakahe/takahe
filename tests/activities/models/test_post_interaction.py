from datetime import timedelta

import pytest
from django.utils import timezone

from activities.models import Post, PostInteraction
from activities.models.post_types import QuestionData
from core.ld import format_ld_date
from users.models import Identity


@pytest.mark.django_db
def test_vote_in_question(identity: Identity, remote_identity: Identity, config_system):
    post = Post.create_local(
        author=identity,
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

    PostInteraction.handle_ap(
        data={
            "id": "https://remote.test/test-actor#votes/11/activity",
            "to": "https://example.com/@test@example.com/",
            "type": "Create",
            "actor": "https://remote.test/test-actor/",
            "object": {
                "id": "https://remote.test/users/test-actor#votes/11",
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
    )

    post.refresh_from_db()

    assert isinstance(post.type_data, QuestionData)
    assert post.type_data.voter_count == 1
    assert post.type_data.options
    assert len(post.type_data.options) == 2
    assert post.type_data.options[0].votes == 1
    assert post.type_data.options[1].votes == 0


@pytest.mark.django_db
def test_vote_in_multiple_choice_question(
    identity: Identity, remote_identity: Identity, config_system
):
    post = Post.create_local(
        author=identity,
        content="<p>Test Question</p>",
        question={
            "type": "Question",
            "mode": "anyOf",
            "options": [
                {"name": "Option 1", "type": "Note", "votes": 0},
                {"name": "Option 2", "type": "Note", "votes": 0},
                {"name": "Option 3", "type": "Note", "votes": 0},
            ],
            "voter_count": 0,
            "end_time": format_ld_date(timezone.now() + timedelta(1)),
        },
    )

    PostInteraction.handle_ap(
        data={
            "id": "https://remote.test/test-actor#votes/12/activity",
            "to": "https://example.com/@test@example.com/",
            "type": "Create",
            "actor": "https://remote.test/test-actor/",
            "object": {
                "id": "https://remote.test/users/test-actor#votes/12",
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
    )

    PostInteraction.handle_ap(
        data={
            "id": "https://remote.test/test-actor#votes/13/activity",
            "to": "https://example.com/@test@example.com/",
            "type": "Create",
            "actor": "https://remote.test/test-actor/",
            "object": {
                "id": "https://remote.test/users/test-actor#votes/13",
                "to": "https://example.com/@test@example.com/",
                "name": "Option 2",
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
    )

    post.refresh_from_db()

    assert isinstance(post.type_data, QuestionData)
    assert post.type_data.voter_count == 1
    assert post.type_data.options
    assert len(post.type_data.options) == 3
    assert post.type_data.options[0].votes == 1
    assert post.type_data.options[1].votes == 1
    assert post.type_data.options[2].votes == 0


@pytest.mark.django_db
def test_multiple_votes_to_single_vote_question(
    identity: Identity, remote_identity: Identity, config_system
):
    post = Post.create_local(
        author=identity,
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

    PostInteraction.by_ap(
        data={
            "id": "https://remote.test/test-actor#votes/14/activity",
            "to": "https://example.com/@test@example.com/",
            "type": "Create",
            "actor": "https://remote.test/test-actor/",
            "object": {
                "id": "https://remote.test/users/test-actor#votes/14",
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

    with pytest.raises(PostInteraction.DoesNotExist) as ex:
        PostInteraction.by_ap(
            data={
                "id": "https://remote.test/test-actor#votes/15/activity",
                "to": "https://example.com/@test@example.com/",
                "type": "Create",
                "actor": "https://remote.test/test-actor/",
                "object": {
                    "id": "https://remote.test/users/test-actor#votes/15",
                    "to": "https://example.com/@test@example.com/",
                    "name": "Option 2",
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
        assert "already voted" in str(ex)


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
                {"name": "Option 1", "type": "Note", "votes": 0},
                {"name": "Option 2", "type": "Note", "votes": 0},
            ],
            "voter_count": 0,
            "end_time": "2022-01-01T23:04:45+00:00",
        },
    )

    with pytest.raises(PostInteraction.DoesNotExist) as ex:
        PostInteraction.by_ap(
            data={
                "id": "https://remote.test/test-actor#votes/16/activity",
                "to": "https://example.com/@test@example.com/",
                "type": "Create",
                "actor": "https://remote.test/test-actor/",
                "object": {
                    "id": "https://remote.test/users/test-actor#votes/16",
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


@pytest.mark.django_db
def test_vote_to_ap(identity: Identity, remote_identity: Identity, config_system):
    post = Post.objects.create(
        author=remote_identity,
        local=False,
        content="<p>Test Question</p>",
        type_data={
            "type": "Question",
            "mode": "oneOf",
            "options": [
                {"name": "Option 1", "type": "Note", "votes": 6},
                {"name": "Option 2", "type": "Note", "votes": 4},
            ],
            "voter_count": 10,
            "end_time": format_ld_date(timezone.now() + timedelta(1)),
        },
    )
    post.refresh_from_db()

    interaction = PostInteraction.create_votes(
        post=post,
        identity=identity,
        choices=[0],
    )[0]

    data = interaction.to_create_ap()
    assert data["object"]["to"] == remote_identity.actor_uri
    assert data["object"]["attributedTo"] == identity.actor_uri
    assert data["object"]["name"] == "Option 1"
    assert data["object"]["inReplyTo"] == post.object_uri
