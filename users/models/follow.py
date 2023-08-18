from typing import Optional

import httpx
from django.db import models, transaction

from core.exceptions import capture_message
from core.ld import canonicalise, get_str_or_id
from core.snowflake import Snowflake
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.block import Block
from users.models.identity import Identity
from users.models.inbox_message import InboxMessage


class FollowStates(StateGraph):
    unrequested = State(try_interval=600)
    pending_approval = State(externally_progressed=True)
    accepting = State(try_interval=24 * 60 * 60)
    rejecting = State(try_interval=24 * 60 * 60)
    accepted = State(externally_progressed=True)
    undone = State(try_interval=24 * 60 * 60)
    pending_removal = State(try_interval=60 * 60)
    removed = State(delete_after=1)

    unrequested.transitions_to(pending_approval)
    unrequested.transitions_to(accepting)
    unrequested.transitions_to(rejecting)
    unrequested.times_out_to(removed, seconds=24 * 60 * 60)
    pending_approval.transitions_to(accepting)
    pending_approval.transitions_to(rejecting)
    pending_approval.transitions_to(pending_removal)
    accepting.transitions_to(accepted)
    accepting.times_out_to(accepted, seconds=7 * 24 * 60 * 60)
    rejecting.transitions_to(pending_removal)
    rejecting.times_out_to(pending_removal, seconds=24 * 60 * 60)
    accepted.transitions_to(rejecting)
    accepted.transitions_to(undone)
    undone.transitions_to(pending_removal)
    pending_removal.transitions_to(removed)

    @classmethod
    def group_active(cls):
        """
        Follows that are active means they are being handled and no need to re-request
        """
        return [cls.unrequested, cls.pending_approval, cls.accepting, cls.accepted]

    @classmethod
    def group_accepted(cls):
        """
        Follows that are accepting/accepted means they should be consider accepted when deliver to followers
        """
        return [cls.accepting, cls.accepted]

    @classmethod
    def handle_unrequested(cls, instance: "Follow"):
        """
        Follows start unrequested as their initial state regardless of local/remote
        """
        if Block.maybe_get(
            source=instance.target, target=instance.source, require_active=True
        ):
            return cls.rejecting
        if not instance.target.local:
            if not instance.source.local:
                # remote follow remote, invalid case
                return cls.removed
            # local follow remote, send Follow to target server
            # Don't try if the other identity didn't fetch yet
            if not instance.target.inbox_uri:
                return
            # Sign it and send it
            try:
                instance.source.signed_request(
                    method="post",
                    uri=instance.target.inbox_uri,
                    body=canonicalise(instance.to_ap()),
                )
            except httpx.RequestError:
                return
            return cls.pending_approval
        # local/remote follow local, check manually_approve
        if instance.target.manually_approves_followers:
            from activities.models import TimelineEvent

            TimelineEvent.add_follow_request(instance.target, instance.source)
            return cls.pending_approval
        return cls.accepting

    @classmethod
    def handle_accepting(cls, instance: "Follow"):
        if not instance.source.local:
            # send an Accept object to the source server
            try:
                instance.target.signed_request(
                    method="post",
                    uri=instance.source.inbox_uri,
                    body=canonicalise(instance.to_accept_ap()),
                )
            except httpx.RequestError:
                return
        from activities.models import TimelineEvent

        TimelineEvent.add_follow(instance.target, instance.source)
        return cls.accepted

    @classmethod
    def handle_rejecting(cls, instance: "Follow"):
        if not instance.source.local:
            # send a Reject object to the source server
            try:
                instance.target.signed_request(
                    method="post",
                    uri=instance.source.inbox_uri,
                    body=canonicalise(instance.to_reject_ap()),
                )
            except httpx.RequestError:
                return
        return cls.pending_removal

    @classmethod
    def handle_undone(cls, instance: "Follow"):
        """
        Delivers the Undo object to the target server
        """
        try:
            if not instance.target.local:
                instance.source.signed_request(
                    method="post",
                    uri=instance.target.inbox_uri,
                    body=canonicalise(instance.to_undo_ap()),
                )
        except httpx.RequestError:
            return
        return cls.pending_removal

    @classmethod
    def handle_pending_removal(cls, instance: "Follow"):
        if instance.target.local:
            from activities.models import TimelineEvent

            TimelineEvent.delete_follow(instance.target, instance.source)
        return cls.removed


class FollowQuerySet(models.QuerySet):
    def active(self):
        query = self.filter(state__in=FollowStates.group_active())
        return query

    def accepted(self):
        query = self.filter(state__in=FollowStates.group_accepted())
        return query


class FollowManager(models.Manager):
    def get_queryset(self):
        return FollowQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def accepted(self):
        return self.get_queryset().accepted()


class Follow(StatorModel):
    """
    When one user (the source) follows other (the target)
    """

    id = models.BigIntegerField(primary_key=True, default=Snowflake.generate_follow)

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

    objects = FollowManager()

    class Meta:
        unique_together = [("source", "target")]
        indexes: list = []  # We need this so Stator can add its own

    def __str__(self):
        return f"#{self.id}: {self.source} → {self.target}"

    ### Alternate fetchers/constructors ###

    @classmethod
    def maybe_get(cls, source, target, require_active=False) -> Optional["Follow"]:
        """
        Returns a follow if it exists between source and target
        """
        try:
            if require_active:
                return Follow.objects.active().get(source=source, target=target)
            else:
                return Follow.objects.get(source=source, target=target)
        except Follow.DoesNotExist:
            return None

    @classmethod
    def create_local(cls, source, target, boosts=True):
        """
        Creates a Follow from a local Identity to the target
        (which can be local or remote).
        """

        if not source.local:
            raise ValueError("You cannot initiate follows from a remote Identity")
        try:
            follow = Follow.objects.get(source=source, target=target)
            if not follow.active:
                follow.state = FollowStates.unrequested
            follow.boosts = boosts
            follow.save()
        except Follow.DoesNotExist:
            with transaction.atomic():
                follow = Follow.objects.create(
                    source=source,
                    target=target,
                    boosts=boosts,
                    uri="",
                    state=FollowStates.unrequested,
                )
                follow.uri = source.actor_uri + f"follow/{follow.pk}/"
                follow.save()
        return follow

    ### Properties ###

    @property
    def active(self):
        return self.state in FollowStates.group_active()

    @property
    def accepted(self):
        return self.state in FollowStates.group_accepted()

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
            "id": f"{self.target.actor_uri}#accept/{self.id}",
            "actor": self.target.actor_uri,
            "object": self.to_ap(),
        }

    def to_reject_ap(self):
        """
        Returns the AP JSON for this objects' rejection.
        """
        return {
            "type": "Reject",
            "id": self.uri + "#reject",
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
    def by_ap(cls, data: str | dict, create=False) -> "Follow":
        """
        Retrieves a Follow instance by its ActivityPub JSON object or its URI.

        Optionally creates one if it's not present.
        Raises DoesNotExist if it's not found and create is False.
        """
        # If it's a string, do the reference resolve
        if isinstance(data, str):
            bits = data.strip("/").split("/")
            if bits[-2] != "follow":
                raise ValueError(f"Unknown Follow object URI: {data}")
            return Follow.objects.get(pk=bits[-1])
        # Otherwise, do object resolve
        else:
            # Resolve source and target and see if a Follow exists
            source = Identity.by_actor_uri(data["actor"], create=create)
            target = Identity.by_actor_uri(get_str_or_id(data["object"]))
            follow = cls.maybe_get(source=source, target=target)
            # If it doesn't exist, create one in the unrequested state
            if follow is None:
                if create:
                    return cls.objects.create(
                        source=source,
                        target=target,
                        uri=data["id"],
                        state=FollowStates.unrequested,
                    )
                else:
                    raise cls.DoesNotExist(
                        f"No follow with source {source} and target {target}", data
                    )
            else:
                return follow

    @classmethod
    def handle_request_ap(cls, data):
        """
        Handles an incoming follow request
        """

        with transaction.atomic():
            try:
                follow = cls.by_ap(data, create=True)
            except Identity.DoesNotExist:
                capture_message(
                    "Identity not found for incoming Follow", extras={"data": data}
                )
                return
            if follow.state == FollowStates.accepted:
                # Likely the source server missed the Accept, send it back again
                follow.transition_perform(FollowStates.accepting)

    @classmethod
    def handle_accept_ap(cls, data):
        """
        Handles an incoming Follow Accept for one of our follows
        """
        # Resolve source and target and see if a Follow exists (it really should)
        try:
            follow = cls.by_ap(data["object"])
        except (cls.DoesNotExist, Identity.DoesNotExist):
            capture_message(
                "Follow or Identity not found for incoming Accept",
                extras={"data": data},
            )
            return

        # Ensure the Accept actor is the Follow's target
        if data["actor"] != follow.target.actor_uri:
            raise ValueError("Accept actor does not match its Follow object", data)
        # If the follow was waiting to be accepted, transition it
        if follow and follow.state == FollowStates.pending_approval:
            follow.transition_perform(FollowStates.accepting)

    @classmethod
    def handle_reject_ap(cls, data):
        """
        Handles an incoming Follow Reject for one of our follows
        """
        # Resolve source and target and see if a Follow exists (it really should)
        try:
            follow = cls.by_ap(data["object"])
        except (cls.DoesNotExist, Identity.DoesNotExist):
            capture_message(
                "Follow or Identity not found for incoming Reject",
                extras={"data": data},
            )
            return

        # Ensure the Accept actor is the Follow's target
        if data["actor"] != follow.target.actor_uri:
            raise ValueError("Reject actor does not match its Follow object", data)
        # Clear timeline if remote target remove local source from their previously accepted follows
        if follow.accepted:
            InboxMessage.create_internal(
                {
                    "type": "ClearTimeline",
                    "object": follow.target.pk,
                    "actor": follow.source.pk,
                }
            )
        # Mark the follow rejected
        follow.transition_perform(FollowStates.rejecting)

    @classmethod
    def handle_undo_ap(cls, data):
        """
        Handles an incoming Follow Undo for one of our follows
        """
        # Resolve source and target and see if a Follow exists (it hopefully does)
        try:
            follow = cls.by_ap(data["object"])
        except (cls.DoesNotExist, Identity.DoesNotExist):
            capture_message(
                "Follow or Identity not found for incoming Undo", extras={"data": data}
            )
            return

        # Ensure the Undo actor is the Follow's source
        if data["actor"] != follow.source.actor_uri:
            raise ValueError("Accept actor does not match its Follow object", data)
        # Delete the follow
        follow.transition_perform(FollowStates.pending_removal)
