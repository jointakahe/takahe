from django.db import models


class TimelineEvent(models.Model):
    """
    Something that has happened to an identity that we want them to see on one
    or more timelines, like posts, likes and follows.
    """

    class Types(models.TextChoices):
        post = "post"
        mention = "mention"
        like = "like"
        follow = "follow"
        boost = "boost"

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
        related_name="timeline_events_about_us",
    )
    subject_identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="timeline_events_about_us",
    )

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        index_together = [
            # This relies on a DB that can use left subsets of indexes
            ("identity", "type", "subject_post", "subject_identity"),
            ("identity", "type", "subject_identity"),
        ]

    ### Alternate constructors ###

    @classmethod
    def add_follow(cls, identity, source_identity):
        """
        Adds a follow to the timeline if it's not there already
        """
        return cls.objects.get_or_create(
            identity=identity,
            type=cls.Types.follow,
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
        )[0]

    @classmethod
    def add_like(cls, identity, post):
        """
        Adds a like to the timeline if it's not there already
        """
        return cls.objects.get_or_create(
            identity=identity,
            type=cls.Types.like,
            subject_post=post,
        )[0]
