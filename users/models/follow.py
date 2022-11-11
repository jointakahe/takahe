from typing import Optional

from django.db import models

from core.ld import canonicalise
from core.signatures import HttpSignature
from stator.models import State, StateField, StateGraph, StatorModel


class FollowStates(StateGraph):
    unrequested = State(try_interval=30)
    local_requested = State(try_interval=24 * 60 * 60)
    remote_requested = State(try_interval=24 * 60 * 60)
    accepted = State(externally_progressed=True)
    undone_locally = State(try_interval=60 * 60)
    undone_remotely = State()

    unrequested.transitions_to(local_requested)
    unrequested.transitions_to(remote_requested)
    local_requested.transitions_to(accepted)
    remote_requested.transitions_to(accepted)
    accepted.transitions_to(undone_locally)
    undone_locally.transitions_to(undone_remotely)

    @classmethod
    async def handle_unrequested(cls, instance: "Follow"):
        # Re-retrieve the follow with more things linked
        follow = await Follow.objects.select_related(
            "source", "source__domain", "target"
        ).aget(pk=instance.pk)
        # Remote follows should not be here
        if not follow.source.local:
            return cls.remote_requested
        # Construct the request
        request = canonicalise(
            {
                "@context": "https://www.w3.org/ns/activitystreams",
                "id": follow.uri,
                "type": "Follow",
                "actor": follow.source.actor_uri,
                "object": follow.target.actor_uri,
            }
        )
        # Sign it and send it
        await HttpSignature.signed_request(
            follow.target.inbox_uri, request, follow.source
        )
        return cls.local_requested

    @classmethod
    async def handle_local_requested(cls, instance: "Follow"):
        # TODO: Resend follow requests occasionally
        pass

    @classmethod
    async def handle_remote_requested(cls, instance: "Follow"):
        # Re-retrieve the follow with more things linked
        follow = await Follow.objects.select_related(
            "source", "source__domain", "target"
        ).aget(pk=instance.pk)
        # Send an accept
        request = canonicalise(
            {
                "@context": "https://www.w3.org/ns/activitystreams",
                "id": follow.target.actor_uri + f"follow/{follow.pk}/#accept",
                "type": "Follow",
                "actor": follow.source.actor_uri,
                "object": {
                    "id": follow.uri,
                    "type": "Follow",
                    "actor": follow.source.actor_uri,
                    "object": follow.target.actor_uri,
                },
            }
        )
        # Sign it and send it
        await HttpSignature.signed_request(
            follow.source.inbox_uri,
            request,
            identity=follow.target,
        )
        return cls.accepted

    @classmethod
    async def handle_undone_locally(cls, instance: "Follow"):
        follow = Follow.objects.select_related(
            "source", "source__domain", "target"
        ).get(pk=instance.pk)
        # Construct the request
        request = canonicalise(
            {
                "@context": "https://www.w3.org/ns/activitystreams",
                "id": follow.uri + "#undo",
                "type": "Undo",
                "actor": follow.source.actor_uri,
                "object": {
                    "id": follow.uri,
                    "type": "Follow",
                    "actor": follow.source.actor_uri,
                    "object": follow.target.actor_uri,
                },
            }
        )
        # Sign it and send it
        await HttpSignature.signed_request(
            follow.target.inbox_uri, request, follow.source
        )
        return cls.undone_remotely


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
        if follow.state == FollowStates.unrequested:
            follow.transition_perform(FollowStates.remote_requested)

    @classmethod
    def remote_accepted(cls, source, target):
        print(f"accepted follow source {source} target {target}")
        follow = cls.maybe_get(source=source, target=target)
        print(f"accepting follow {follow}")
        if follow and follow.state in [
            FollowStates.unrequested,
            FollowStates.local_requested,
        ]:
            follow.transition_perform(FollowStates.accepted)
            print("accepted")
