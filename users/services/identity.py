from django.db import models
from django.template.defaultfilters import linebreaks_filter

from activities.models import FanOut
from core.files import resize_image
from core.html import FediverseHtmlParser
from users.models import (
    Block,
    BlockStates,
    Domain,
    Follow,
    FollowStates,
    Identity,
    InboxMessage,
    User,
)


class IdentityService:
    """
    High-level helper methods for doing things to identities
    """

    def __init__(self, identity: Identity):
        self.identity = identity

    @classmethod
    def create(
        cls,
        user: User,
        username: str,
        domain: Domain,
        name: str,
        discoverable: bool = True,
    ) -> Identity:
        identity = Identity.objects.create(
            actor_uri=f"https://{domain.uri_domain}/@{username}@{domain.domain}/",
            username=username,
            domain=domain,
            name=name,
            local=True,
            discoverable=discoverable,
        )
        identity.users.add(user)
        identity.generate_keypair()
        # Send fanouts to all admin identities
        for admin_identity in cls.admin_identities():
            FanOut.objects.create(
                type=FanOut.Types.identity_created,
                identity=admin_identity,
                subject_identity=identity,
            )
        return identity

    @classmethod
    def admin_identities(cls) -> models.QuerySet[Identity]:
        return Identity.objects.filter(users__admin=True).distinct()

    def following(self) -> models.QuerySet[Identity]:
        return (
            Identity.objects.active()
            .filter(inbound_follows__source=self.identity)
            .not_deleted()
            .order_by("username")
            .select_related("domain")
        )

    def followers(self) -> models.QuerySet[Identity]:
        return (
            Identity.objects.filter(outbound_follows__target=self.identity)
            .not_deleted()
            .order_by("username")
            .select_related("domain")
        )

    def follow_from(self, from_identity: Identity, boosts=True) -> Follow:
        """
        Follows a user (or does nothing if already followed).
        Returns the follow.
        """
        if from_identity == self.identity:
            raise ValueError("You cannot follow yourself")
        return Follow.create_local(from_identity, self.identity, boosts=boosts)

    def unfollow_from(self, from_identity: Identity):
        """
        Unfollows a user (or does nothing if not followed).
        """
        if from_identity == self.identity:
            raise ValueError("You cannot unfollow yourself")
        existing_follow = Follow.maybe_get(from_identity, self.identity)
        if existing_follow:
            existing_follow.transition_perform(FollowStates.undone)
            InboxMessage.create_internal(
                {
                    "type": "ClearTimeline",
                    "actor": from_identity.pk,
                    "object": self.identity.pk,
                }
            )

    def block_from(self, from_identity: Identity) -> Block:
        """
        Blocks a user.
        """
        if from_identity == self.identity:
            raise ValueError("You cannot block yourself")
        self.unfollow_from(from_identity)
        block = Block.create_local_block(from_identity, self.identity)
        InboxMessage.create_internal(
            {
                "type": "ClearTimeline",
                "actor": from_identity.pk,
                "object": self.identity.pk,
                "fullErase": True,
            }
        )
        return block

    def unblock_from(self, from_identity: Identity):
        """
        Unlocks a user
        """
        if from_identity == self.identity:
            raise ValueError("You cannot unblock yourself")
        existing_block = Block.maybe_get(from_identity, self.identity, mute=False)
        if existing_block and existing_block.active:
            existing_block.transition_perform(BlockStates.undone)

    def mute_from(
        self,
        from_identity: Identity,
        duration: int = 0,
        include_notifications: bool = False,
    ) -> Block:
        """
        Mutes a user.
        """
        if from_identity == self.identity:
            raise ValueError("You cannot mute yourself")
        return Block.create_local_mute(
            from_identity,
            self.identity,
            duration=duration or None,
            include_notifications=include_notifications,
        )

    def unmute_from(self, from_identity: Identity):
        """
        Unmutes a user
        """
        if from_identity == self.identity:
            raise ValueError("You cannot unmute yourself")
        existing_block = Block.maybe_get(from_identity, self.identity, mute=True)
        if existing_block and existing_block.active:
            existing_block.transition_perform(BlockStates.undone)

    def relationships(self, from_identity: Identity):
        """
        Returns a dict of any active relationships from the given identity.
        """
        return {
            "outbound_follow": Follow.maybe_get(
                from_identity, self.identity, require_active=True
            ),
            "inbound_follow": Follow.maybe_get(
                self.identity, from_identity, require_active=True
            ),
            "outbound_block": Block.maybe_get(
                from_identity, self.identity, mute=False, require_active=True
            ),
            "inbound_block": Block.maybe_get(
                self.identity, from_identity, mute=False, require_active=True
            ),
            "outbound_mute": Block.maybe_get(
                from_identity, self.identity, mute=True, require_active=True
            ),
        }

    def mastodon_json_relationship(self, from_identity: Identity):
        """
        Returns a Relationship object for the from_identity's relationship
        with this identity.
        """
        relationships = self.relationships(from_identity)
        return {
            "id": self.identity.pk,
            "following": relationships["outbound_follow"] is not None,
            "followed_by": relationships["inbound_follow"] is not None,
            "showing_reblogs": (
                relationships["outbound_follow"]
                and relationships["outbound_follow"].boosts
                or False
            ),
            "notifying": False,
            "blocking": relationships["outbound_block"] is not None,
            "blocked_by": relationships["inbound_block"] is not None,
            "muting": relationships["outbound_mute"] is not None,
            "muting_notifications": False,
            "requested": False,
            "domain_blocking": False,
            "endorsed": False,
            "note": (
                relationships["outbound_follow"]
                and relationships["outbound_follow"].note
                or ""
            ),
        }

    def set_summary(self, summary: str):
        """
        Safely sets a summary and turns linebreaks into HTML
        """
        if summary:
            self.identity.summary = FediverseHtmlParser(linebreaks_filter(summary)).html
        else:
            self.identity.summary = None
        self.identity.save()

    def set_icon(self, file):
        """
        Sets the user's avatar image
        """
        self.identity.icon.save(
            file.name,
            resize_image(file, size=(400, 400)),
        )

    def set_image(self, file):
        """
        Sets the user's header image
        """
        self.identity.image.save(
            file.name,
            resize_image(file, size=(1500, 500)),
        )
