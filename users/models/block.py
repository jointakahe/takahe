import datetime
from typing import Optional

import httpx
from django.db import models, transaction
from django.utils import timezone

from core.ld import canonicalise, get_str_or_id
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.identity import Identity


class BlockStates(StateGraph):
    new = State(try_interval=600)
    sent = State(externally_progressed=True)
    awaiting_expiry = State(try_interval=60 * 60, attempt_immediately=False)
    undone = State(try_interval=60 * 60, delete_after=86400 * 7)
    undone_sent = State(delete_after=86400)

    new.transitions_to(sent)
    new.transitions_to(awaiting_expiry)
    sent.transitions_to(undone)
    awaiting_expiry.transitions_to(undone)
    # We don't really care if the other end accepts our block
    new.times_out_to(sent, seconds=86400 * 7)
    undone.transitions_to(undone_sent)

    @classmethod
    def group_active(cls):
        return [cls.new, cls.sent, cls.awaiting_expiry]

    @classmethod
    async def handle_new(cls, instance: "Block"):
        """
        Block that are new need us to deliver the Block object
        to the target server.
        """
        # Mutes don't send but might need expiry
        if instance.mute:
            return cls.awaiting_expiry
        # Fetch more info
        block = await instance.afetch_full()
        # Remote blocks should not be here, local blocks just work
        if not block.source.local or block.target.local:
            return cls.sent
        # Don't try if the other identity didn't fetch yet
        if not block.target.inbox_uri:
            return
        # Sign it and send it
        try:
            await block.source.signed_request(
                method="post",
                uri=block.target.inbox_uri,
                body=canonicalise(block.to_ap()),
            )
        except httpx.RequestError:
            return
        return cls.sent

    @classmethod
    async def handle_awaiting_expiry(cls, instance: "Block"):
        """
        Checks to see if there is an expiry we should undo
        """
        if instance.expires and instance.expires <= timezone.now():
            return cls.undone

    @classmethod
    async def handle_undone(cls, instance: "Block"):
        """
        Delivers the Undo object to the target server
        """
        block = await instance.afetch_full()
        # Remote blocks should not be here, mutes don't send, local blocks just work
        if not block.source.local or block.target.local or instance.mute:
            return cls.undone_sent
        try:
            await block.source.signed_request(
                method="post",
                uri=block.target.inbox_uri,
                body=canonicalise(block.to_undo_ap()),
            )
        except httpx.RequestError:
            return
        return cls.undone_sent


class BlockQuerySet(models.QuerySet):
    def active(self):
        query = self.filter(state__in=BlockStates.group_active())
        return query


class BlockManager(models.Manager):
    def get_queryset(self):
        return BlockQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()


class Block(StatorModel):
    """
    When one user (the source) mutes or blocks another (the target)
    """

    state = StateField(BlockStates)

    source = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="outbound_blocks",
    )

    target = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="inbound_blocks",
    )

    uri = models.CharField(blank=True, null=True, max_length=500)

    # If it is a mute, we will stop delivering any activities from target to
    # source, but we will still deliver activities from source to target.
    # A full block (mute=False) stops activities both ways.
    mute = models.BooleanField()
    include_notifications = models.BooleanField(default=False)

    expires = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = BlockManager()

    class Meta:
        unique_together = [("source", "target", "mute")]

    def __str__(self):
        return f"#{self.id}: {self.source} blocks {self.target}"

    ### Alternate fetchers/constructors ###

    @classmethod
    def maybe_get(
        cls, source, target, mute=False, require_active=False
    ) -> Optional["Block"]:
        """
        Returns a Block if it exists between source and target
        """
        try:
            if require_active:
                return cls.objects.active().get(source=source, target=target, mute=mute)
            else:
                return cls.objects.get(source=source, target=target, mute=mute)
        except cls.DoesNotExist:
            return None

    @classmethod
    def create_local_block(cls, source, target) -> "Block":
        """
        Creates or updates a full Block from a local Identity to the target
        (which can be local or remote).
        """
        if not source.local:
            raise ValueError("You cannot block from a remote Identity")
        block = cls.maybe_get(source=source, target=target, mute=False)
        if block is not None:
            if not block.active:
                block.state = BlockStates.new  # type:ignore
            block.save()
        else:
            with transaction.atomic():
                block = cls.objects.create(
                    source=source,
                    target=target,
                    mute=False,
                )
                block.uri = source.actor_uri + f"block/{block.pk}/"
                block.save()
        return block

    @classmethod
    def create_local_mute(
        cls,
        source,
        target,
        duration=None,
        include_notifications=False,
    ) -> "Block":
        """
        Creates or updates a muting Block from a local Identity to the target
        (which can be local or remote).
        """
        if not source.local:
            raise ValueError("You cannot mute from a remote Identity")
        block = cls.maybe_get(source=source, target=target, mute=True)
        if block is not None:
            if not block.active:
                block.state = BlockStates.new  # type:ignore
            if duration:
                block.expires = timezone.now() + datetime.timedelta(seconds=duration)
            block.include_notifications = include_notifications
            block.save()
        else:
            with transaction.atomic():
                block = cls.objects.create(
                    source=source,
                    target=target,
                    mute=True,
                    include_notifications=include_notifications,
                    expires=(
                        timezone.now() + datetime.timedelta(seconds=duration)
                        if duration
                        else None
                    ),
                )
                block.uri = source.actor_uri + f"block/{block.pk}/"
                block.save()
        return block

    ### Properties ###

    @property
    def active(self):
        return self.state in BlockStates.group_active()

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await Block.objects.select_related(
            "source", "source__domain", "target"
        ).aget(pk=self.pk)

    ### ActivityPub (outbound) ###

    def to_ap(self):
        """
        Returns the AP JSON for this object
        """
        if self.mute:
            raise ValueError("Cannot send mutes over ActivityPub")
        return {
            "type": "Block",
            "id": self.uri,
            "actor": self.source.actor_uri,
            "object": self.target.actor_uri,
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
    def by_ap(cls, data: str | dict, create=False) -> "Block":
        """
        Retrieves a Block instance by its ActivityPub JSON object or its URI.

        Optionally creates one if it's not present.
        Raises KeyError if it's not found and create is False.
        """
        # If it's a string, do the reference resolve
        if isinstance(data, str):
            bits = data.strip("/").split("/")
            if bits[-2] != "block":
                raise ValueError(f"Unknown Block object URI: {data}")
            return Block.objects.get(pk=bits[-1])
        # Otherwise, do the object resolve
        else:
            # Resolve source and target and see if a Block exists
            source = Identity.by_actor_uri(data["actor"], create=create)
            target = Identity.by_actor_uri(get_str_or_id(data["object"]))
            block = cls.maybe_get(source=source, target=target, mute=False)
            # If it doesn't exist, create one in the sent state
            if block is None:
                if create:
                    return cls.objects.create(
                        source=source,
                        target=target,
                        uri=data["id"],
                        mute=False,
                        state=BlockStates.sent,
                    )
                else:
                    raise cls.DoesNotExist(
                        f"No block with source {source} and target {target}", data
                    )
            else:
                return block

    @classmethod
    def handle_ap(cls, data):
        """
        Handles an incoming Block notification
        """
        with transaction.atomic():
            cls.by_ap(data, create=True)

    @classmethod
    def handle_undo_ap(cls, data):
        """
        Handles an incoming Block Undo
        """
        # Resolve source and target and see if a Follow exists (it hopefully does)
        try:
            block = cls.by_ap(data["object"])
        except KeyError:
            raise ValueError("No Block locally for incoming Undo", data)
        # Check the block's source is the actor
        if data["actor"] != block.source.actor_uri:
            raise ValueError("Undo actor does not match its Block object", data)
        # Delete the follow
        block.delete()
