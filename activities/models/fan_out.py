import httpx
from asgiref.sync import sync_to_async
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
    async def handle_new(cls, instance: "FanOut"):
        """
        Sends the fan-out to the right inbox.
        """

        fan_out = await instance.afetch_full()

        # Don't try to fan out to identities that are not fetched yet
        if not (fan_out.identity.local or fan_out.identity.inbox_uri):
            return

        match (fan_out.type, fan_out.identity.local):
            # Handle creating/updating local posts
            case ((FanOut.Types.post | FanOut.Types.post_edited), True):
                post = await fan_out.subject_post.afetch_full()
                # If the author of the post is blocked or muted, skip out
                if (
                    await Block.objects.active()
                    .filter(source=fan_out.identity, target=post.author)
                    .aexists()
                ):
                    return cls.skipped
                # Make a timeline event directly
                # If it's a reply, we only add it if we follow at least one
                # of the people mentioned AND the author, or we're mentioned,
                # or it's a reply to us or the author
                add = True
                mentioned = {identity.id for identity in post.mentions.all()}
                if post.in_reply_to:
                    followed = await sync_to_async(set)(
                        fan_out.identity.outbound_follows.filter(
                            state__in=FollowStates.group_active()
                        ).values_list("target_id", flat=True)
                    )
                    interested_in = followed.union(
                        {post.author_id, fan_out.identity_id}
                    )
                    add = (post.author_id in followed) and (
                        bool(mentioned.intersection(interested_in))
                    )
                if add:
                    await sync_to_async(TimelineEvent.add_post)(
                        identity=fan_out.identity,
                        post=post,
                    )
                # We might have been mentioned
                if (
                    fan_out.identity.id in mentioned
                    and fan_out.identity_id != post.author_id
                ):
                    await sync_to_async(TimelineEvent.add_mentioned)(
                        identity=fan_out.identity,
                        post=post,
                    )

            # Handle sending remote posts create
            case (FanOut.Types.post, False):
                post = await fan_out.subject_post.afetch_full()
                # Sign it and send it
                try:
                    await post.author.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_create_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending remote posts update
            case (FanOut.Types.post_edited, False):
                post = await fan_out.subject_post.afetch_full()
                # Sign it and send it
                try:
                    await post.author.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_update_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle deleting local posts
            case (FanOut.Types.post_deleted, True):
                post = await fan_out.subject_post.afetch_full()
                if fan_out.identity.local:
                    # Remove all timeline events mentioning it
                    await TimelineEvent.objects.filter(
                        identity=fan_out.identity,
                        subject_post=post,
                    ).adelete()

            # Handle sending remote post deletes
            case (FanOut.Types.post_deleted, False):
                post = await fan_out.subject_post.afetch_full()
                # Send it to the remote inbox
                try:
                    await post.author.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(post.to_delete_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle local boosts/likes
            case (FanOut.Types.interaction, True):
                interaction = await fan_out.subject_post_interaction.afetch_full()
                # If the author of the interaction is blocked or their notifications
                # are muted, skip out
                if (
                    await Block.objects.active()
                    .filter(
                        models.Q(mute=False) | models.Q(include_notifications=True),
                        source=fan_out.identity,
                        target=interaction.identity,
                    )
                    .aexists()
                ):
                    return cls.skipped
                # If blocked/muted the underlying post author, skip out
                if (
                    await Block.objects.active()
                    .filter(
                        source=fan_out.identity,
                        target_id=interaction.post.author_id,
                    )
                    .aexists()
                ):
                    return cls.skipped
                # Make a timeline event directly
                await sync_to_async(TimelineEvent.add_post_interaction)(
                    identity=fan_out.identity,
                    interaction=interaction,
                )

            # Handle sending remote boosts/likes
            case (FanOut.Types.interaction, False):
                interaction = await fan_out.subject_post_interaction.afetch_full()
                # Send it to the remote inbox
                try:
                    await interaction.identity.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(interaction.to_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle undoing local boosts/likes
            case (FanOut.Types.undo_interaction, True):  # noqa:F841
                interaction = await fan_out.subject_post_interaction.afetch_full()

                # Delete any local timeline events
                await sync_to_async(TimelineEvent.delete_post_interaction)(
                    identity=fan_out.identity,
                    interaction=interaction,
                )

            # Handle sending remote undoing boosts/likes
            case (FanOut.Types.undo_interaction, False):  # noqa:F841
                interaction = await fan_out.subject_post_interaction.afetch_full()
                # Send an undo to the remote inbox
                try:
                    await interaction.identity.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(interaction.to_undo_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending identity edited to remote
            case (FanOut.Types.identity_edited, False):
                identity = await fan_out.subject_identity.afetch_full()
                try:
                    await identity.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(fan_out.subject_identity.to_update_ap()),
                    )
                except httpx.RequestError:
                    return

            # Handle sending identity deleted to remote
            case (FanOut.Types.identity_deleted, False):
                identity = await fan_out.subject_identity.afetch_full()
                try:
                    await identity.signed_request(
                        method="post",
                        uri=(
                            fan_out.identity.shared_inbox_uri
                            or fan_out.identity.inbox_uri
                        ),
                        body=canonicalise(fan_out.subject_identity.to_delete_ap()),
                    )
                except httpx.RequestError:
                    return

            # Sending identity edited/deleted to local is a no-op
            case (FanOut.Types.identity_edited, True):
                pass
            case (FanOut.Types.identity_deleted, True):
                pass

            case _:
                raise ValueError(
                    f"Cannot fan out with type {fan_out.type} local={fan_out.identity.local}"
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

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return (
            await FanOut.objects.select_related(
                "identity",
                "subject_post",
                "subject_post_interaction",
                "subject_identity",
                "subject_identity__domain",
            )
            .prefetch_related(
                "subject_post__emojis",
            )
            .aget(pk=self.pk)
        )
