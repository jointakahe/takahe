import pytest

from activities.models import Post, TimelineEvent
from activities.services import PostService
from users.models import Identity, InboxMessage


@pytest.mark.django_db
@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("reaction", ["\U0001F607"])
def test_react_notification(
    identity: Identity,
    other_identity: Identity,
    remote_identity: Identity,
    stator,
    local: bool,
    reaction: str,
):
    """
    Ensures that a reaction of a local Post notifies its author.

    This mostly ensures that basic reaction flows happen.
    """
    post = Post.create_local(author=identity, content="I love birds!")
    if local:
        PostService(post).like_as(other_identity, reaction)
    else:
        message = {
            "id": "test",
            "type": "Like",
            "actor": remote_identity.actor_uri,
            "object": post.object_uri,
            "content": reaction,
        }
        InboxMessage.objects.create(message=message)

    interactor = other_identity if local else remote_identity

    # Run stator thrice - to receive the post, make fanouts and then process them
    stator.run_single_cycle()
    stator.run_single_cycle()
    stator.run_single_cycle()

    # Verify we got an event
    event = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).first()
    assert event
    assert event.subject_identity == interactor
    assert event.subject_post_interaction.value == reaction


@pytest.mark.django_db
@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("reaction", ["\U0001F607"])
def test_react_duplicate(
    identity: Identity,
    other_identity: Identity,
    remote_identity: Identity,
    stator,
    local: bool,
    reaction: str,
):
    """
    Ensures that if we receive the same reaction from the same actor multiple times,
    only one notification and interaction are produced.
    """
    post = Post.create_local(author=identity, content="I love birds!")
    for _ in range(3):
        if local:
            PostService(post).like_as(other_identity, reaction)
        else:
            message = {
                "id": "test",
                "type": "Like",
                "actor": remote_identity.actor_uri,
                "object": post.object_uri,
                "content": reaction,
            }
            InboxMessage.objects.create(message=message)

    interactor = other_identity if local else remote_identity

    # Running stator 3 times for each interaction. Not sure what's the right number.
    for _ in range(9):
        stator.run_single_cycle()

    # Verify we got an event
    events = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).all()

    assert len(events) == 1
    (event,) = events

    assert event.subject_identity == interactor
    assert event.subject_post_interaction.value == reaction


@pytest.mark.django_db
@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("reaction", ["\U0001F607"])
def test_react_undo(
    identity: Identity,
    other_identity: Identity,
    remote_identity: Identity,
    stator,
    local: bool,
    reaction: str,
):
    """
    Ensures basic un-reacting.
    """
    post = Post.create_local(author=identity, content="I love birds!")
    if local:
        PostService(post).like_as(other_identity, reaction)
    else:
        message = {
            "id": "test",
            "type": "Like",
            "actor": remote_identity.actor_uri,
            "object": post.object_uri,
            "content": reaction,
        }
        InboxMessage.objects.create(message=message)

    # Run stator thrice - to receive the post, make fanouts and then process them
    stator.run_single_cycle()
    stator.run_single_cycle()
    stator.run_single_cycle()

    # Verify we got an event
    events = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).all()
    assert len(events) == 1

    if local:
        PostService(post).unlike_as(other_identity, reaction)
    else:
        message = {
            "id": "test/undo",
            "type": "Undo",
            "actor": remote_identity.actor_uri,
            "object": {
                "id": "test",
                "type": "Like",
                "actor": remote_identity.actor_uri,
                "object": post.object_uri,
                "content": reaction,
            },
        }
        InboxMessage.objects.create(message=message)

    # Run stator thrice - to receive the post, make fanouts and then process them
    stator.run_single_cycle()
    stator.run_single_cycle()
    stator.run_single_cycle()

    # Verify the event was removed.
    events = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).all()
    assert len(events) == 0


@pytest.mark.django_db
@pytest.mark.parametrize("local", [True, False])
def test_react_undo_mismatched(
    identity: Identity,
    other_identity: Identity,
    remote_identity: Identity,
    stator,
    local: bool,
):
    """
    Ensures that un-reacting deletes the right reaction.
    """
    post = Post.create_local(author=identity, content="I love birds!")
    if local:
        PostService(post).like_as(other_identity, "foo")
    else:
        message = {
            "id": "test",
            "type": "Like",
            "actor": remote_identity.actor_uri,
            "object": post.object_uri,
            "content": "foo",
        }
        InboxMessage.objects.create(message=message)

    # Run stator thrice - to receive the post, make fanouts and then process them
    stator.run_single_cycle()
    stator.run_single_cycle()
    stator.run_single_cycle()

    # Verify we got an event
    events = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).all()
    assert len(events) == 1

    if local:
        PostService(post).unlike_as(other_identity, "bar")
    else:
        message = {
            "id": "test/undo",
            "type": "Undo",
            "actor": remote_identity.actor_uri,
            "object": {
                # AstraLuma: I'm actually unsure if this test should use the same or different ID.
                "id": "test2",
                "type": "Like",
                "actor": remote_identity.actor_uri,
                "object": post.object_uri,
                "content": "bar",
            },
        }
        InboxMessage.objects.create(message=message)

    # Run stator thrice - to receive the post, make fanouts and then process them
    stator.run_single_cycle()
    stator.run_single_cycle()
    stator.run_single_cycle()

    # Verify the event was removed.
    events = TimelineEvent.objects.filter(
        type=TimelineEvent.Types.liked, identity=identity
    ).all()
    assert len(events) == 1


# TODO: Test that multiple reactions can be added and deleted correctly

# TODO: How should plain likes and reactions from the same source be handled?
# Specifically if we receive an unlike without a specific reaction.

# Hm, If Misskey is single-reaction, will it send Like interactions for changes
# in reaction? Then we're expected to overwrite that users previous interaction
# rather than create a new one.
