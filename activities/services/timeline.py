from django.db import models

from activities.models import (
    Hashtag,
    Post,
    PostInteraction,
    PostInteractionStates,
    TimelineEvent,
)
from activities.services import PostService
from users.models import Identity


class TimelineService:
    """
    Timelines and stuff!
    """

    def __init__(self, identity: Identity | None):
        self.identity = identity

    @classmethod
    def event_queryset(cls):
        return TimelineEvent.objects.select_related(
            "subject_post",
            "subject_post__author",
            "subject_post__author__domain",
            "subject_identity",
            "subject_identity__domain",
            "subject_post_interaction",
            "subject_post_interaction__identity",
            "subject_post_interaction__identity__domain",
        ).prefetch_related(
            "subject_post__attachments",
            "subject_post__mentions",
            "subject_post__emojis",
        )

    def home(self) -> models.QuerySet[TimelineEvent]:
        return (
            self.event_queryset()
            .filter(
                identity=self.identity,
                type__in=[TimelineEvent.Types.post, TimelineEvent.Types.boost],
            )
            .order_by("-created")
        )

    def local(self) -> models.QuerySet[Post]:
        queryset = (
            PostService.queryset()
            .local_public()
            .filter(author__restriction=Identity.Restriction.none)
            .order_by("-id")
        )
        if self.identity is not None:
            queryset = queryset.filter(author__domain=self.identity.domain)
        return queryset

    def federated(self) -> models.QuerySet[Post]:
        return (
            PostService.queryset()
            .public()
            .filter(author__restriction=Identity.Restriction.none)
            .order_by("-id")
        )

    def hashtag(self, hashtag: str | Hashtag) -> models.QuerySet[Post]:
        return (
            PostService.queryset()
            .public()
            .filter(author__restriction=Identity.Restriction.none)
            .tagged_with(hashtag)
            .order_by("-id")
        )

    def notifications(self, types: list[str]) -> models.QuerySet[TimelineEvent]:
        return (
            self.event_queryset()
            .filter(identity=self.identity, type__in=types, dismissed=False)
            .order_by("-created")
        )

    def identity_public(
        self,
        identity: Identity,
        include_boosts: bool = True,
        include_replies: bool = True,
    ):
        """
        Returns timeline events with all of an identity's publicly visible posts
        and their boosts
        """
        filter = models.Q(
            type=TimelineEvent.Types.post,
            subject_post__author=identity,
            subject_post__visibility__in=[
                Post.Visibilities.public,
                Post.Visibilities.local_only,
                Post.Visibilities.unlisted,
            ],
        )
        if include_boosts:
            filter = filter | models.Q(
                type=TimelineEvent.Types.boost, subject_identity=identity
            )
        if not include_replies:
            filter = filter & models.Q(subject_post__in_reply_to__isnull=True)
        return (
            self.event_queryset()
            .filter(
                filter,
                identity=identity,
            )
            .order_by("-created")
        )

    def identity_pinned(self) -> models.QuerySet[Post]:
        """
        Return all pinned posts that are publicly visible for an identity
        """
        return (
            PostService.queryset()
            .public()
            .filter(
                interactions__identity=self.identity,
                interactions__type=PostInteraction.Types.pin,
                interactions__state__in=PostInteractionStates.group_active(),
            )
        )

    def likes(self) -> models.QuerySet[Post]:
        """
        Return all liked posts for an identity
        """
        return (
            PostService.queryset()
            .filter(
                interactions__identity=self.identity,
                interactions__type=PostInteraction.Types.like,
                interactions__state__in=PostInteractionStates.group_active(),
            )
            .order_by("-id")
        )

    def bookmarks(self) -> models.QuerySet[Post]:
        """
        Return all bookmarked posts for an identity
        """
        return (
            PostService.queryset()
            .filter(bookmarks__identity=self.identity)
            .order_by("-id")
        )
