from typing import cast

from users.models import Follow, FollowStates, Identity


class IdentityService:
    """
    High-level helper methods for doing things to identities
    """

    def __init__(self, identity: Identity):
        self.identity = identity

    def follow_from(self, from_identity: Identity) -> Follow:
        """
        Follows a user (or does nothing if already followed).
        Returns the follow.
        """
        existing_follow = Follow.maybe_get(from_identity, self.identity)
        if not existing_follow:
            Follow.create_local(from_identity, self.identity)
        elif existing_follow.state in [
            FollowStates.undone,
            FollowStates.undone_remotely,
            FollowStates.failed,
        ]:
            existing_follow.transition_perform(FollowStates.unrequested)
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
        return {
            "id": self.identity.pk,
            "following": self.identity.inbound_follows.filter(
                source=from_identity,
                state__in=FollowStates.group_active(),
            ).exists(),
            "followed_by": self.identity.outbound_follows.filter(
                target=from_identity,
                state__in=FollowStates.group_active(),
            ).exists(),
            "showing_reblogs": True,
            "notifying": False,
            "blocking": False,
            "blocked_by": False,
            "muting": False,
            "muting_notifications": False,
            "requested": False,
            "domain_blocking": False,
            "endorsed": False,
            "note": "",
        }
