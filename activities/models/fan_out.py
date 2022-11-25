from asgiref.sync import sync_to_async
from django.db import models

from activities.models.timeline_event import TimelineEvent
from core.ld import canonicalise
from stator.models import State, StateField, StateGraph, StatorModel


class FanOutStates(StateGraph):
    new = State(try_interval=300)
    sent = State()

    new.transitions_to(sent)

    @classmethod
    async def handle_new(cls, instance: "FanOut"):
        """
        Sends the fan-out to the right inbox.
        """
        fan_out = await instance.afetch_full()
        # Handle Posts
        if fan_out.type == FanOut.Types.post:
            post = await fan_out.subject_post.afetch_full()
            if fan_out.identity.local:
                # Make a timeline event directly
                # TODO: Exclude replies to people we don't follow
                await sync_to_async(TimelineEvent.add_post)(
                    identity=fan_out.identity,
                    post=post,
                )
                # We might have been mentioned
                if fan_out.identity in list(post.mentions.all()):
                    TimelineEvent.add_mentioned(
                        identity=fan_out.identity,
                        post=post,
                    )
            else:
                # Sign it and send it
                await post.author.signed_request(
                    method="post",
                    uri=fan_out.identity.inbox_uri,
                    body=canonicalise(post.to_create_ap()),
                )
        # Handle deleting posts
        elif fan_out.type == FanOut.Types.post_deleted:
            post = await fan_out.subject_post.afetch_full()
            if fan_out.identity.local:
                # Remove all timeline events mentioning it
                await TimelineEvent.objects.filter(
                    identity=fan_out.identity,
                    subject_post=post,
                ).adelete()
            else:
                # Send it to the remote inbox
                await post.author.signed_request(
                    method="post",
                    uri=fan_out.identity.inbox_uri,
                    body=canonicalise(post.to_delete_ap()),
                )
        # Handle boosts/likes
        elif fan_out.type == FanOut.Types.interaction:
            interaction = await fan_out.subject_post_interaction.afetch_full()
            if fan_out.identity.local:
                # Make a timeline event directly
                await sync_to_async(TimelineEvent.add_post_interaction)(
                    identity=fan_out.identity,
                    interaction=interaction,
                )
            else:
                # Send it to the remote inbox
                await interaction.identity.signed_request(
                    method="post",
                    uri=fan_out.identity.inbox_uri,
                    body=canonicalise(interaction.to_ap()),
                )
        # Handle undoing boosts/likes
        elif fan_out.type == FanOut.Types.undo_interaction:
            interaction = await fan_out.subject_post_interaction.afetch_full()
            if fan_out.identity.local:
                # Delete any local timeline events
                await sync_to_async(TimelineEvent.delete_post_interaction)(
                    identity=fan_out.identity,
                    interaction=interaction,
                )
            else:
                # Send an undo to the remote inbox
                await interaction.identity.signed_request(
                    method="post",
                    uri=fan_out.identity.inbox_uri,
                    body=canonicalise(interaction.to_undo_ap()),
                )
        else:
            raise ValueError(f"Cannot fan out with type {fan_out.type}")
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

    state = StateField(FanOutStates)

    # The user this event is targeted at
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

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await FanOut.objects.select_related(
            "identity",
            "subject_post",
            "subject_post_interaction",
        ).aget(pk=self.pk)
