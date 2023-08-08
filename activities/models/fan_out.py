import httpx
from django.db import models

from activities.models.timeline_event import TimelineEvent
from core.ld import canonicalise
from stator.models import State, StateField, StateGraph, StatorModel
from users.models import Block, FollowStates


class FanOutStates(StateGraph):
    new = State(try_interval=600)
    sent = State(delete_after=86400)
    skipped = State(delete_after=86400)
    failed = State(delete_after=86400)

    new.transitions_to(sent)
    new.transitions_to(skipped)
    new.times_out_to(failed, seconds=86400 * 3)

    @classmethod
    def handle_new(cls, instance: "FanOut"):
        """
        Sends the fan-out to the right inbox.
        """

        # Don't try to fan out to identities that are not fetched yet
        if not (instance.identity.local or instance.identity.inbox_uri):
            return

        match (instance.type, instance.identity.local):
            # Handle creating/updating local posts
            case ((FanOut.Types.post | FanOut.Types.post_edited), True):
                post = instance.subject_post
                # If the author of the post is blocked or muted, skip out
                if (
                    Block.objects.active()
                    .filter(source=instance.identity, target=post.author)
                    .exists()
                ):
                    return cls.skipped
                # Make a timeline event directly
                # If it's a reply, we only add it if we follow at least one
                # of the people mentioned AND the author, or we're mentioned,
                # or it's a reply to us or the author
                add = True
                mentioned = {identity.id for identity in post.mentions.all()}
                if post.in_reply_to:
                    followed = set(
                        instance.identity.outbound_follows.filter(
                            state__in=FollowStates.group_active()
                        ).values_list("target_id", flat=True)
                    )
                    interested_in = followed.union(
                        {post.author_id, instance.identity_id}
                    )
                    add = (post.author_id in followed) and (
                        bool(mentioned.intersection(interested_in))
                    )
                if add:
                    TimelineEvent.add_post(
                        identity=instance.identity,
                        post=post,
                    )
                # We might have been mentioned
                if (
                    instance.identity.id in mentioned
                    and instance.identity_id != post.author_id
                ):
                    TimelineEvent.add_mentioned(
                        identity=instance.identity,
                        post=post,
                    )

            # Handle sending remote posts create
            case (FanOut.Types.post, False):
                post = instance.subject_post
                # Sign it and send it
                try:
                    post.author.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_create_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending remote posts update
            case (FanOut.Types.post_edited, False):
                post = instance.subject_post
                # Sign it and send it
                try:
                    post.author.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_update_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle deleting local posts
            case (FanOut.Types.post_deleted, True):
                post = instance.subject_post
                if instance.identity.local:
                    # Remove all timeline events mentioning it
                    TimelineEvent.objects.filter(
                        identity=instance.identity,
                        subject_post=post,
                    ).delete()

            # Handle sending remote post deletes
            case (FanOut.Types.post_deleted, False):
                post = instance.subject_post
                # Send it to the remote inbox
                try:
                    post.author.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_delete_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle local boosts/likes
            case (FanOut.Types.interaction, True):
                interaction = instance.subject_post_interaction
                # If the author of the interaction is blocked or their notifications
                # are muted, skip out
                if (
                    Block.objects.active()
                    .filter(
                        models.Q(mute=False) | models.Q(include_notifications=True),
                        source=instance.identity,
                        target=interaction.identity,
                    )
                    .exists()
                ):
                    return cls.skipped
                # If blocked/muted the underlying post author, skip out
                if (
                    Block.objects.active()
                    .filter(
                        source=instance.identity,
                        target_id=interaction.post.author_id,
                    )
                    .exists()
                ):
                    return cls.skipped
                # Make a timeline event directly
                TimelineEvent.add_post_interaction(
                    identity=instance.identity,
                    interaction=interaction,
                )

            # Handle sending remote boosts/likes/votes/pins
            case (FanOut.Types.interaction, False):
                interaction = instance.subject_post_interaction
                # Send it to the remote inbox
                try:
                    if interaction.type == interaction.Types.vote:
                        body = interaction.to_create_ap()
                    elif interaction.type == interaction.Types.pin:
                        body = interaction.to_add_ap()
                    else:
                        body = interaction.to_ap()
                    interaction.identity.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(body),
                    )
                except httpx.RequestError:
                    return

            # Handle undoing local boosts/likes
            case (FanOut.Types.undo_interaction, True):  # noqa:F841
                interaction = instance.subject_post_interaction

                # Delete any local timeline events
                TimelineEvent.delete_post_interaction(
                    identity=instance.identity,
                    interaction=interaction,
                )

            # Handle sending remote undoing boosts/likes/pins
            case (FanOut.Types.undo_interaction, False):  # noqa:F841
                interaction = instance.subject_post_interaction
                # Send an undo to the remote inbox
                try:
                    if interaction.type == interaction.Types.pin:
                        body = interaction.to_remove_ap()
                    else:
                        body = interaction.to_undo_ap()
                    interaction.identity.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(body),
                    )
                except httpx.RequestError:
                    return

            # Handle sending identity edited to remote
            case (FanOut.Types.identity_edited, False):
                identity = instance.subject_identity
                try:
                    identity.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(instance.subject_identity.to_update_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending identity deleted to remote
            case (FanOut.Types.identity_deleted, False):
                identity = instance.subject_identity
                try:
                    identity.signed_request(
                        method="post",
                        uri=(
                            instance.identity.shared_inbox_uri
                            or instance.identity.inbox_uri
                        ),
                        body=canonicalise(instance.subject_identity.to_delete_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending identity moved to remote
            case (FanOut.Types.identity_moved, False):
                raise NotImplementedError()

            # Sending identity edited/deleted to local is a no-op
            case (FanOut.Types.identity_edited, True):
                pass
            case (FanOut.Types.identity_deleted, True):
                pass

            # Created identities make a timeline event
            case (FanOut.Types.identity_created, True):
                TimelineEvent.add_identity_created(
                    identity=instance.identity,
                    new_identity=instance.subject_identity,
                )

            case _:
                raise ValueError(
                    f"Cannot fan out with type {instance.type} local={instance.identity.local}"
                )

        return cls.sent


class FanOut(StatorModel):
    """
    An activity that needs to get to an inbox somewhere.
    """

    class Types(models.TextChoices):
        post = "post"
        post_edited = "post_edited"
        post_deleted = "post_deleted"
        interaction = "interaction"
        undo_interaction = "undo_interaction"
        identity_edited = "identity_edited"
        identity_deleted = "identity_deleted"
        identity_created = "identity_created"
        identity_moved = "identity_moved"

    state = StateField(FanOutStates)

    # The user this event is targeted at
    # We always need this, but if there is a shared inbox URL on the user
    # we'll deliver to that and won't have fanouts for anyone else with the
    # same one.
    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="fan_outs",
    )

    # What type of activity it is
    type = models.CharField(max_length=100, choices=Types.choices)

    # Links to the appropriate objects
    subject_post = models.ForeignKey(
        "activities.Post",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="fan_outs",
    )
    subject_post_interaction = models.ForeignKey(
        "activities.PostInteraction",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="fan_outs",
    )
    subject_identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="subject_fan_outs",
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
