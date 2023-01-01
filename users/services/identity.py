from typing import cast

from django.db import models
from django.template.defaultfilters import linebreaks_filter

from core.html import strip_html
from users.models import Follow, FollowStates, Identity


class IdentityService:
    """
    High-level helper methods for doing things to identities
    """

    def __init__(self, identity: Identity):
        self.identity = identity

    def following(self) -> models.QuerySet[Identity]:
        return (
            Identity.objects.filter(inbound_follows__source=self.identity)
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
        existing_follow = Follow.maybe_get(from_identity, self.identity)
        if not existing_follow:
            return Follow.create_local(from_identity, self.identity, boosts=boosts)
        elif existing_follow.state not in FollowStates.group_active():
            existing_follow.transition_perform(FollowStates.unrequested)

        if existing_follow.boosts != boosts:
            existing_follow.boosts = boosts
            existing_follow.save()
        return cast(Follow, existing_follow)

    def unfollow_from(self, from_identity: Identity):
        """
        Unfollows a user (or does nothing if not followed).
        """
        existing_follow = Follow.maybe_get(from_identity, self.identity)
        if existing_follow:
            existing_follow.transition_perform(FollowStates.undone)

    def mastodon_json_relationship(self, from_identity: Identity):
        """
        Returns a Relationship object for the from_identity's relationship
        with this identity.
        """

        follow = self.identity.inbound_follows.filter(
            source=from_identity,
            state__in=FollowStates.group_active(),
        ).first()

        return {
            "id": self.identity.pk,
            "following": follow is not None,
            "followed_by": self.identity.outbound_follows.filter(
                target=from_identity,
                state__in=FollowStates.group_active(),
            ).exists(),
            "showing_reblogs": follow and follow.boosts or False,
            "notifying": False,
            "blocking": False,
            "blocked_by": False,
            "muting": False,
            "muting_notifications": False,
            "requested": False,
            "domain_blocking": False,
            "endorsed": False,
            "note": (follow and follow.note) or "",
        }

    def set_summary(self, summary: str):
        """
        Safely sets a summary and turns linebreaks into HTML
        """
        if summary:
            self.identity.summary = linebreaks_filter(strip_html(summary))
        else:
            self.identity.summary = None
        self.identity.save()
