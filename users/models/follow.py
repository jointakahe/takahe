from typing import Optional

import httpx
from django.db import models, transaction

from core.ld import canonicalise, get_str_or_id
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.identity import Identity


class FollowStates(StateGraph):
    unrequested = State(try_interval=600)
    local_requested = State(try_interval=24 * 60 * 60)
    remote_requested = State(try_interval=24 * 60 * 60)
    accepted = State(externally_progressed=True)
    undone = State(try_interval=60 * 60)
    undone_remotely = State()
    failed = State()
    rejected = State()

    unrequested.transitions_to(local_requested)
    unrequested.transitions_to(remote_requested)
    unrequested.times_out_to(failed, seconds=86400 * 7)
    local_requested.transitions_to(accepted)
    local_requested.transitions_to(rejected)
    remote_requested.transitions_to(accepted)
    accepted.transitions_to(undone)
    undone.transitions_to(undone_remotely)

    @classmethod
    def group_active(cls):
        return [cls.unrequested, cls.local_requested, cls.accepted]

    @classmethod
    async def handle_unrequested(cls, instance: "Follow"):
        """
        Follows that are unrequested need us to deliver the Follow object
        to the target server.
        """
        follow = await instance.afetch_full()
        # Remote follows should not be here
        if not follow.source.local:
            return cls.remote_requested
        if follow.target.local:
            return cls.accepted
        # Don't try if the other identity didn't fetch yet
        if not follow.target.inbox_uri:
            return
        # Sign it and send it
        try:
            await follow.source.signed_request(
                method="post",
                uri=follow.target.inbox_uri,
                body=canonicalise(follow.to_ap()),
            )
        except httpx.RequestError:
            return
        return cls.local_requested

    @classmethod
    async def handle_local_requested(cls, instance: "Follow"):
        # TODO: Resend follow requests occasionally
        pass

    @classmethod
    async def handle_remote_requested(cls, instance: "Follow"):
        """
        Items in remote_requested need us to send an Accept object to the
        source server.
        """
        follow = await instance.afetch_full()
        try:
            await follow.target.signed_request(
                method="post",
                uri=follow.source.inbox_uri,
                body=canonicalise(follow.to_accept_ap()),
            )
        except httpx.RequestError:
            return
        return cls.accepted

    @classmethod
    async def handle_undone(cls, instance: "Follow"):
        """
        Delivers the Undo object to the target server
        """
        follow = await instance.afetch_full()
        try:
            await follow.source.signed_request(
                method="post",
                uri=follow.target.inbox_uri,
                body=canonicalise(follow.to_undo_ap()),
            )
        except httpx.RequestError:
            return
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

    boosts = models.BooleanField(
        default=True, help_text="Also follow boosts from this user"
    )

    uri = models.CharField(blank=True, null=True, max_length=500)
    note = models.TextField(blank=True, null=True)

    state = StateField(FollowStates)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source", "target")]

    def __str__(self):
        return f"#{self.id}: {self.source} → {self.target}"

    ### Alternate fetchers/constructors ###

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
    def create_local(cls, source, target, boosts=True):
        """
        Creates a Follow from a local Identity to the target
        (which can be local or remote).
        """
        from activities.models import TimelineEvent

        if not source.local:
            raise ValueError("You cannot initiate follows from a remote Identity")
        try:
            follow = Follow.objects.get(source=source, target=target)
            if follow.boosts != boosts:
                follow.boosts = boosts
                follow.save()
        except Follow.DoesNotExist:
            follow = Follow.objects.create(
                source=source, target=target, boosts=boosts, uri=""
            )
            follow.uri = source.actor_uri + f"follow/{follow.pk}/"
            # TODO: Local follow approvals
            if target.local:
                follow.state = FollowStates.accepted
                TimelineEvent.add_follow(follow.target, follow.source)
            follow.save()
        return follow

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await Follow.objects.select_related(
            "source", "source__domain", "target"
        ).aget(pk=self.pk)

    ### Helper properties ###

    @property
    def pending(self):
        return self.state in [FollowStates.unrequested, FollowStates.local_requested]

    ### ActivityPub (outbound) ###

    def to_ap(self):
        """
        Returns the AP JSON for this object
        """
        return {
            "type": "Follow",
            "id": self.uri,
            "actor": self.source.actor_uri,
            "object": self.target.actor_uri,
        }

    def to_accept_ap(self):
        """
        Returns the AP JSON for this objects' accept.
        """
        return {
            "type": "Accept",
            "id": self.uri + "#accept",
            "actor": self.target.actor_uri,
            "object": self.to_ap(),
        }

    def to_undo_ap(self):
        """
        Returns the AP JSON for this objects' undo.
        """
        return {
            "type": "Undo",
            "id": self.uri + "#undo",
            "actor": self.source.actor_uri,
            "object": self.to_ap(),
        }

    ### ActivityPub (inbound) ###

    @classmethod
    def by_ap(cls, data, create=False) -> "Follow":
        """
        Retrieves a Follow instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises KeyError if it's not found and create is False.
        """
        # Resolve source and target and see if a Follow exists
        source = Identity.by_actor_uri(data["actor"], create=create)
        target = Identity.by_actor_uri(get_str_or_id(data["object"]))
        follow = cls.maybe_get(source=source, target=target)
        # If it doesn't exist, create one in the remote_requested state
        if follow is None:
            if create:
                return cls.objects.create(
                    source=source,
                    target=target,
                    uri=data["id"],
                    state=FollowStates.remote_requested,
                )
            else:
                raise KeyError(
                    f"No follow with source {source} and target {target}", data
                )
        else:
            return follow

    @classmethod
    def handle_request_ap(cls, data):
        """
        Handles an incoming follow request
        """
        from activities.models import TimelineEvent

        with transaction.atomic():
            follow = cls.by_ap(data, create=True)
            # Force it into remote_requested so we send an accept
            follow.transition_perform(FollowStates.remote_requested)
            # Add a timeline event
            TimelineEvent.add_follow(follow.target, follow.source)

    @classmethod
    def handle_accept_ap(cls, data):
        """
        Handles an incoming Follow Accept for one of our follows
        """
        # Ensure the Accept actor is the Follow's object
        if data["actor"] != data["object"]["object"]:
            raise ValueError("Accept actor does not match its Follow object", data)
        # Resolve source and target and see if a Follow exists (it really should)
        try:
            follow = cls.by_ap(data["object"])
        except KeyError:
            raise ValueError("No Follow locally for incoming Accept", data)
        # If the follow was waiting to be accepted, transition it
        if follow and follow.state in [
            FollowStates.unrequested,
            FollowStates.local_requested,
        ]:
            follow.transition_perform(FollowStates.accepted)

    @classmethod
    def handle_accept_ref_ap(cls, data):
        """
        Handles an incoming Follow Accept for one of our follows where there is
        only an object URI reference.
        """
        # Ensure the object ref is in a format we expect
        bits = data["object"].strip("/").split("/")
        if bits[-2] != "follow":
            raise ValueError(f"Unknown Follow object URI in Accept: {data['object']}")
        # Retrieve the object by PK
        follow = cls.objects.get(pk=bits[-1])
        # Ensure it's from the right actor
        if data["actor"] != follow.target.actor_uri:
            raise ValueError("Accept actor does not match its Follow object", data)
        # If the follow was waiting to be accepted, transition it
        if follow.state in [
            FollowStates.unrequested,
            FollowStates.local_requested,
        ]:
            follow.transition_perform(FollowStates.accepted)

    @classmethod
    def handle_undo_ap(cls, data):
        """
        Handles an incoming Follow Undo for one of our follows
        """
        # Ensure the Undo actor is the Follow's actor
        if data["actor"] != data["object"]["actor"]:
            raise ValueError("Undo actor does not match its Follow object", data)
        # Resolve source and target and see if a Follow exists (it hopefully does)
        try:
            follow = cls.by_ap(data["object"])
        except KeyError:
            raise ValueError("No Follow locally for incoming Undo", data)
        # Delete the follow
        follow.delete()

    @classmethod
    def handle_reject_ap(cls, data):
        """
        Handles an incoming Follow Reject for one of our follows
        """
        # Ensure the Accept actor is the Follow's object
        if data["actor"] != data["object"]["object"]:
            raise ValueError("Accept actor does not match its Follow object", data)
        # Resolve source and target and see if a Follow exists (it really should)
        try:
            follow = cls.by_ap(data["object"])
        except KeyError:
            raise ValueError("No Follow locally for incoming Reject", data)
        # Mark the follow rejected
        follow.transition_perform(FollowStates.rejected)
