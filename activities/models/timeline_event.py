from django.db import models
from django.utils import timezone

from core.ld import format_ld_date


class TimelineEvent(models.Model):
    """
    Something that has happened to an identity that we want them to see on one
    or more timelines, like posts, likes and follows.
    """

    class Types(models.TextChoices):
        post = "post"
        boost = "boost"  # A boost from someone (post substitute)
        mentioned = "mentioned"
        liked = "liked"  # Someone liking one of our posts
        followed = "followed"
        boosted = "boosted"  # Someone boosting one of our posts
        announcement = "announcement"  # Server announcement

    # The user this event is for
    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="timeline_events",
    )

    # What type of event it is
    type = models.CharField(max_length=100, choices=Types.choices)

    # The subject of the event (which is used depends on the type)
    subject_post = models.ForeignKey(
        "activities.Post",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="timeline_events",
    )
    subject_post_interaction = models.ForeignKey(
        "activities.PostInteraction",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="timeline_events",
    )
    subject_identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="timeline_events_about_us",
    )

    published = models.DateTimeField(default=timezone.now)
    seen = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        index_together = [
            # This relies on a DB that can use left subsets of indexes
            ("identity", "type", "subject_post", "subject_identity"),
            ("identity", "type", "subject_identity"),
            ("identity", "created"),
        ]

    ### Alternate constructors ###

    @classmethod
    def add_follow(cls, identity, source_identity):
        """
        Adds a follow to the timeline if it's not there already
        """
        return cls.objects.get_or_create(
            identity=identity,
            type=cls.Types.followed,
            subject_identity=source_identity,
        )[0]

    @classmethod
    def add_post(cls, identity, post):
        """
        Adds a post to the timeline if it's not there already
        """
        return cls.objects.get_or_create(
            identity=identity,
            type=cls.Types.post,
            subject_post=post,
            defaults={"published": post.published or post.created},
        )[0]

    @classmethod
    def add_mentioned(cls, identity, post):
        """
        Adds a mention of identity by post
        """
        return cls.objects.get_or_create(
            identity=identity,
            type=cls.Types.mentioned,
            subject_post=post,
            subject_identity=post.author,
            defaults={"published": post.published or post.created},
        )[0]

    @classmethod
    def add_post_interaction(cls, identity, interaction):
        """
        Adds a boost/like to the timeline if it's not there already.

        For boosts, may make two objects - one "boost" and one "boosted".
        It'll return the "boost" in that case.
        """
        if interaction.type == interaction.Types.like:
            return cls.objects.get_or_create(
                identity=identity,
                type=cls.Types.liked,
                subject_post_id=interaction.post_id,
                subject_identity_id=interaction.identity_id,
                subject_post_interaction=interaction,
            )[0]
        elif interaction.type == interaction.Types.boost:
            # If the boost is on one of our posts, then that's a boosted too
            if interaction.post.author_id == identity.id:
                return cls.objects.get_or_create(
                    identity=identity,
                    type=cls.Types.boosted,
                    subject_post_id=interaction.post_id,
                    subject_identity_id=interaction.identity_id,
                    subject_post_interaction=interaction,
                )[0]
            return cls.objects.get_or_create(
                identity=identity,
                type=cls.Types.boost,
                subject_post_id=interaction.post_id,
                subject_identity_id=interaction.identity_id,
                subject_post_interaction=interaction,
            )[0]

    @classmethod
    def delete_post_interaction(cls, identity, interaction):
        if interaction.type == interaction.Types.like:
            cls.objects.filter(
                identity=identity,
                type=cls.Types.liked,
                subject_post_id=interaction.post_id,
                subject_identity_id=interaction.identity_id,
            ).delete()
        elif interaction.type == interaction.Types.boost:
            cls.objects.filter(
                identity=identity,
                type__in=[cls.Types.boosted, cls.Types.boost],
                subject_post_id=interaction.post_id,
                subject_identity_id=interaction.identity_id,
            ).delete()

    ### Mastodon Client API ###

    def to_mastodon_notification_json(self, interactions=None):
        result = {
            "id": self.pk,
            "created_at": format_ld_date(self.created),
            "account": self.subject_identity.to_mastodon_json(),
        }
        if self.type == self.Types.liked:
            result["type"] = "favourite"
            result["status"] = self.subject_post.to_mastodon_json(
                interactions=interactions
            )
        elif self.type == self.Types.boosted:
            result["type"] = "reblog"
            result["status"] = self.subject_post.to_mastodon_json(
                interactions=interactions
            )
        elif self.type == self.Types.mentioned:
            result["type"] = "mention"
            result["status"] = self.subject_post.to_mastodon_json(
                interactions=interactions
            )
        elif self.type == self.Types.followed:
            result["type"] = "follow"
        else:
            raise ValueError(f"Cannot convert {self.type} to notification JSON")
        return result

    def to_mastodon_status_json(self, interactions=None):
        if self.type == self.Types.post:
            return self.subject_post.to_mastodon_json(interactions=interactions)
        elif self.type == self.Types.boost:
            return self.subject_post_interaction.to_mastodon_status_json(
                interactions=interactions
            )
        else:
            raise ValueError(f"Cannot make status JSON for type {self.type}")
