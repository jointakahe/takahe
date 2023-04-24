from datetime import timedelta

import pytest
from django.utils import timezone

from activities.models import Post, PostInteraction, PostInteractionStates
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


@pytest.mark.django_db
def test_handle_add_ap(remote_identity: Identity, config_system):
    post = Post.create_local(
        author=remote_identity,
        content="<p>Hello World</p>",
    )
    add_ap = {
        "type": "Add",
        "actor": "https://remote.test/test-actor/",
        "object": post.object_uri,
        "target": "https://remote.test/test-actor/collections/featured/",
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            {
                "toot": "http://joinmastodon.org/ns#",
                "Emoji": "toot:Emoji",
                "Hashtag": "as:Hashtag",
                "blurhash": "toot:blurhash",
                "featured": {"@id": "toot:featured", "@type": "@id"},
                "sensitive": "as:sensitive",
                "focalPoint": {"@id": "toot:focalPoint", "@container": "@list"},
                "votersCount": "toot:votersCount",
                "manuallyApprovesFollowers": "as:manuallyApprovesFollowers",
            },
            "https://w3id.org/security/v1",
        ],
    }

    # mismatched target with identity's featured_collection_uri is a no-op
    PostInteraction.handle_add_ap(data=add_ap | {"target": "different-target"})
    assert (
        PostInteraction.objects.filter(
            type=PostInteraction.Types.pin, post=post
        ).count()
        == 0
    )

    # successfully add a pin interaction
    PostInteraction.handle_add_ap(
        data=add_ap,
    )
    assert (
        PostInteraction.objects.filter(
            type=PostInteraction.Types.pin, post=post
        ).count()
        == 1
    )

    # second identical Add activity is a no-op
    PostInteraction.handle_add_ap(
        data=add_ap,
    )
    assert (
        PostInteraction.objects.filter(
            type=PostInteraction.Types.pin, post=post
        ).count()
        == 1
    )

    # new Add activity for inactive interaction creates a new one
    old_interaction = PostInteraction.objects.get(
        type=PostInteraction.Types.pin, post=post
    )
    old_interaction.transition_perform(PostInteractionStates.undone_fanned_out)
    PostInteraction.handle_add_ap(
        data=add_ap,
    )
    new_interaction = PostInteraction.objects.get(
        type=PostInteraction.Types.pin,
        post=post,
        state__in=PostInteractionStates.group_active(),
    )
    assert new_interaction.pk != old_interaction.pk


@pytest.mark.django_db
def test_handle_remove_ap(remote_identity: Identity, config_system):
    post = Post.create_local(
        author=remote_identity,
        content="<p>Hello World</p>",
    )
    interaction = PostInteraction.objects.create(
        type=PostInteraction.Types.pin,
        identity=remote_identity,
        post=post,
    )
    remove_ap = {
        "type": "Remove",
        "actor": "https://remote.test/test-actor/",
        "object": post.object_uri,
        "target": "https://remote.test/test-actor/collections/featured/",
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            {
                "toot": "http://joinmastodon.org/ns#",
                "Emoji": "toot:Emoji",
                "Hashtag": "as:Hashtag",
                "blurhash": "toot:blurhash",
                "featured": {"@id": "toot:featured", "@type": "@id"},
                "sensitive": "as:sensitive",
                "focalPoint": {"@id": "toot:focalPoint", "@container": "@list"},
                "votersCount": "toot:votersCount",
                "manuallyApprovesFollowers": "as:manuallyApprovesFollowers",
            },
            "https://w3id.org/security/v1",
        ],
    }

    interaction.refresh_from_db()

    # mismatched target with identity's featured_collection_uri is a no-op
    initial_state = interaction.state
    PostInteraction.handle_remove_ap(data=remove_ap | {"target": "different-target"})
    interaction.refresh_from_db()
    assert initial_state == interaction.state

    # successfully remove a pin interaction
    PostInteraction.handle_remove_ap(
        data=remove_ap,
    )
    interaction.refresh_from_db()
    assert interaction.state == PostInteractionStates.undone_fanned_out

    # Remove activity on unknown post is a no-op
    PostInteraction.handle_remove_ap(data=remove_ap | {"object": "unknown-post"})
