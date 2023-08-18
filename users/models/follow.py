from typing import Optional

import httpx
from django.db import models, transaction

from core.exceptions import capture_message
from core.ld import canonicalise, get_str_or_id
from core.snowflake import Snowflake
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.identity import Identity


class FollowStates(StateGraph):
    unrequested = State(try_interval=600)
    local_requested = State(try_interval=24 * 60 * 60)
    remote_requested = State(try_interval=24 * 60 * 60)
    accepted = State(externally_progressed=True)
    undone = State(try_interval=60 * 60)
    undone_remotely = State(delete_after=24 * 60 * 60)
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
    def handle_unrequested(cls, instance: "Follow"):
        """
        Follows that are unrequested need us to deliver the Follow object
        to the target server.
        """
        # Remote follows should not be here
        if not instance.source.local:
            return cls.remote_requested
        if instance.target.local:
            return cls.accepted
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
        return cls.local_requested

    @classmethod
    def handle_local_requested(cls, instance: "Follow"):
        # TODO: Resend follow requests occasionally
        pass

    @classmethod
    def handle_remote_requested(cls, instance: "Follow"):
        """
        Items in remote_requested need us to send an Accept object to the
        source server.
        """
        try:
            instance.target.signed_request(
                method="post",
                uri=instance.source.inbox_uri,
                body=canonicalise(instance.to_accept_ap()),
            )
        except httpx.RequestError:
            return
        return cls.accepted

    @classmethod
    def handle_undone(cls, instance: "Follow"):
        """
        Delivers the Undo object to the target server
        """
        try:
            instance.source.signed_request(
                method="post",
                uri=instance.target.inbox_uri,
                body=canonicalise(instance.to_undo_ap()),
            )
        except httpx.RequestError:
            return
        return cls.undone_remotely


class FollowQuerySet(models.QuerySet):
    def active(self):
        query = self.filter(state__in=FollowStates.group_active())
        return query


class FollowManager(models.Manager):
    def get_queryset(self):
        return FollowQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()


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
        from activities.models import TimelineEvent

        if not source.local:
            raise ValueError("You cannot initiate follows from a remote Identity")
        try:
            follow = Follow.objects.get(source=source, target=target)
            if not follow.active:
                follow.state = (
                    FollowStates.accepted if target.local else FollowStates.unrequested
                )
            follow.boosts = boosts
            follow.save()
        except Follow.DoesNotExist:
            with transaction.atomic():
                follow = Follow.objects.create(
                    source=source,
                    target=target,
                    boosts=boosts,
                    uri="",
                    state=(
                        FollowStates.accepted
                        if target.local
                        else FollowStates.unrequested
                    ),
                )
                follow.uri = source.actor_uri + f"follow/{follow.pk}/"
                # TODO: Local follow approvals
                if target.local:
                    TimelineEvent.add_follow(follow.target, follow.source)
                follow.save()
        return follow

    ### Properties ###

    @property
    def pending(self):
        return self.state in [FollowStates.unrequested, FollowStates.local_requested]

    @property
    def active(self):
        return self.state in FollowStates.group_active()

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
        from activities.models import TimelineEvent

        with transaction.atomic():
            try:
                follow = cls.by_ap(data, create=True)
            except Identity.DoesNotExist:
                capture_message(
                    "Identity not found for incoming Follow", extras={"data": data}
                )
                return

            # Force it into remote_requested so we send an accept
            follow.transition_perform(FollowStates.remote_requested)
            # Add a timeline event
            TimelineEvent.add_follow(follow.target, follow.source)

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
        if follow and follow.state in [
            FollowStates.unrequested,
            FollowStates.local_requested,
        ]:
            follow.transition_perform(FollowStates.accepted)

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
        # Mark the follow rejected
        follow.transition_perform(FollowStates.rejected)

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
        follow.delete()
