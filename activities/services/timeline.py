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
        return (
            TimelineEvent.objects.select_related(
                "subject_post",
                "subject_post__author",
                "subject_post__author__domain",
                "subject_identity",
                "subject_identity__domain",
                "subject_post_interaction",
                "subject_post_interaction__identity",
                "subject_post_interaction__identity__domain",
            )
            .prefetch_related(
                "subject_post__attachments",
                "subject_post__mentions",
                "subject_post__emojis",
            )
            .annotate(
                like_count=models.Count(
                    "subject_post__interactions",
                    filter=models.Q(
                        subject_post__interactions__type=PostInteraction.Types.like,
                        subject_post__interactions__state__in=PostInteractionStates.group_active(),
                    ),
                ),
                boost_count=models.Count(
                    "subject_post__interactions",
                    filter=models.Q(
                        subject_post__interactions__type=PostInteraction.Types.boost,
                        subject_post__interactions__state__in=PostInteractionStates.group_active(),
                    ),
                ),
            )
        )

    def home(self) -> models.QuerySet[TimelineEvent]:
        return (
            self.event_queryset()
            .filter(
                identity=self.identity,
                type__in=[TimelineEvent.Types.post, TimelineEvent.Types.boost],
            )
            .order_by("-published")
        )

    def local(self) -> models.QuerySet[Post]:
        return (
            PostService.queryset()
            .local_public()
            .filter(author__restriction=Identity.Restriction.none)
            .order_by("-published")
        )

    def federated(self) -> models.QuerySet[Post]:
        return (
            PostService.queryset()
            .public()
            .filter(author__restriction=Identity.Restriction.none)
            .order_by("-published")
        )

    def hashtag(self, hashtag: str | Hashtag) -> models.QuerySet[Post]:
        return (
            PostService.queryset()
            .public()
            .filter(author__restriction=Identity.Restriction.none)
            .tagged_with(hashtag)
            .order_by("-published")
        )

    def notifications(self, types: list[str]) -> models.QuerySet[TimelineEvent]:
        return (
            self.event_queryset()
            .filter(identity=self.identity, type__in=types)
            .order_by("-published")
        )

    def identity_public(self, identity: Identity):
        """
        Returns all publically visible posts for an identity
        """
        return (
            PostService.queryset()
            .filter(author=identity)
            .unlisted(include_replies=True)
            .order_by("-created")
        )
