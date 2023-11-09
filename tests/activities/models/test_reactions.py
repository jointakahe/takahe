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
    Ensures that a like of a local Post notifies its author
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

    # Implement any blocks
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
