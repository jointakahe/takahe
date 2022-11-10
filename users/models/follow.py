from typing import Optional

from django.db import models

from stator.models import State, StateField, StateGraph, StatorModel


class FollowStates(StateGraph):
    unrequested = State(try_interval=30)
    requested = State(try_interval=24 * 60 * 60)
    accepted = State()

    unrequested.transitions_to(requested)
    requested.transitions_to(accepted)

    @classmethod
    async def handle_unrequested(cls, instance: "Follow"):
        print("Would have tried to follow on", instance)

    @classmethod
    async def handle_requested(cls, instance: "Follow"):
        print("Would have tried to requested on", instance)


class Follow(StatorModel):
    """
    When one user (the source) follows other (the target)
    """

    source = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="outbound_follows",
    )
    target = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="inbound_follows",
    )

    uri = models.CharField(blank=True, null=True, max_length=500)
    note = models.TextField(blank=True, null=True)

    state = StateField(FollowStates)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source", "target")]

    @classmethod
    def maybe_get(cls, source, target) -> Optional["Follow"]:
        """
        Returns a follow if it exists between source and target
        """
        try:
            return Follow.objects.get(source=source, target=target)
        except Follow.DoesNotExist:
            return None

    @classmethod
    def create_local(cls, source, target):
        """
        Creates a Follow from a local Identity to the target
        (which can be local or remote).
        """
        if not source.local:
            raise ValueError("You cannot initiate follows from a remote Identity")
        try:
            follow = Follow.objects.get(source=source, target=target)
        except Follow.DoesNotExist:
            follow = Follow.objects.create(source=source, target=target, uri="")
            follow.uri = source.actor_uri + f"follow/{follow.pk}/"
            # TODO: Local follow approvals
            if target.local:
                follow.state = FollowStates.accepted
            follow.save()
        return follow

    @classmethod
    def remote_created(cls, source, target, uri):
        follow = cls.maybe_get(source=source, target=target)
        if follow is None:
            follow = Follow.objects.create(source=source, target=target, uri=uri)
        if follow.state == FollowStates.fresh:
            follow.transition_perform(FollowStates.requested)

    @classmethod
    def remote_accepted(cls, source, target):
        follow = cls.maybe_get(source=source, target=target)
        if follow and follow.state == FollowStates.requested:
            follow.transition_perform(FollowStates.accepted)
