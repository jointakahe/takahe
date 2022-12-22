from django.db import models

from activities.models import Hashtag, Post, PostInteraction, TimelineEvent
from users.models import Identity


class TimelineService:
    """
    Timelines and stuff!
    """

    def __init__(self, identity: Identity | None):
        self.identity = identity

    def home(self) -> models.QuerySet[TimelineEvent]:
        return (
            TimelineEvent.objects.filter(
                identity=self.identity,
                type__in=[TimelineEvent.Types.post, TimelineEvent.Types.boost],
            )
            .select_related(
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
                        subject_post__interactions__type=PostInteraction.Types.like
                    ),
                ),
                boost_count=models.Count(
                    "subject_post__interactions",
                    filter=models.Q(
                        subject_post__interactions__type=PostInteraction.Types.boost
                    ),
                ),
            )
            .order_by("-published")
        )

    def local(self) -> models.QuerySet[Post]:
        return (
            Post.objects.local_public()
            .not_hidden()
            .filter(author__restriction=Identity.Restriction.none)
            .select_related("author", "author__domain")
            .prefetch_related("attachments", "mentions", "emojis")
            .annotate(
                like_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.like),
                ),
                boost_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.boost),
                ),
            )
            .order_by("-published")
        )

    def federated(self) -> models.QuerySet[Post]:
        return (
            Post.objects.public()
            .not_hidden()
            .filter(author__restriction=Identity.Restriction.none)
            .select_related("author", "author__domain")
            .prefetch_related("attachments", "mentions", "emojis")
            .annotate(
                like_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.like),
                ),
                boost_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.boost),
                ),
            )
            .order_by("-published")
        )

    def hashtag(self, hashtag: str | Hashtag) -> models.QuerySet[Post]:
        return (
            Post.objects.public()
            .not_hidden()
            .filter(author__restriction=Identity.Restriction.none)
            .tagged_with(hashtag)
            .select_related("author", "author__domain")
            .prefetch_related("attachments", "mentions")
            .annotate(
                like_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.like),
                ),
                boost_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.boost),
                ),
            )
            .order_by("-published")
        )

    def notifications(self, types: list[str]) -> models.QuerySet[TimelineEvent]:
        return (
            TimelineEvent.objects.filter(identity=self.identity, type__in=types)
            .order_by("-published")
            .select_related(
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
                "subject_post__emojis",
                "subject_post__mentions",
                "subject_post__attachments",
            )
            .annotate(
                like_count=models.Count(
                    "subject_post__interactions",
                    filter=models.Q(
                        subject_post__interactions__type=PostInteraction.Types.like
                    ),
                ),
                boost_count=models.Count(
                    "subject_post__interactions",
                    filter=models.Q(
                        subject_post__interactions__type=PostInteraction.Types.boost
                    ),
                ),
            )
        )

    def identity_public(self, identity: Identity):
        """
        Returns all publically visible posts for an identity
        """
        return (
            identity.posts.not_hidden()
            .unlisted(include_replies=True)
            .select_related("author")
            .prefetch_related("attachments")
            .select_related("author", "author__domain")
            .prefetch_related("attachments", "mentions")
            .annotate(
                like_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.like),
                ),
                boost_count=models.Count(
                    "interactions",
                    filter=models.Q(interactions__type=PostInteraction.Types.boost),
                ),
            )
            .order_by("-created")
        )
