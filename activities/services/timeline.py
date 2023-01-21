from django.db import models

from activities.models import Hashtag, Post, PostInteraction, TimelineEvent
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
        return (
            PostService.queryset()
            .local_public()
            .filter(author__restriction=Identity.Restriction.none)
            .order_by("-id")
        )

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
            .filter(identity=self.identity, type__in=types)
            .order_by("-created")
        )

    def identity_public(self, identity: Identity):
        """
        Returns all publically visible posts for an identity
        """
        return (
            PostService.queryset()
            .filter(author=identity)
            .unlisted(include_replies=True)
            .order_by("-id")
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
            )
            .order_by("-id")
        )
