from typing import Optional

from django.db import models


class HashtagFollowQuerySet(models.QuerySet):
    def by_hashtags(self, hashtags: list[str]):
        return self.filter(hashtag_id__in=hashtags)

    def by_identity(self, identity):
        return self.filter(identity=identity)


class HashtagFollowManager(models.Manager):
    def get_queryset(self):
        return HashtagFollowQuerySet(self.model, using=self._db)

    def by_hashtags(self, hashtags: list[str]):
        return self.get_queryset().by_hashtags(hashtags)

    def by_identity(self, identity):
        return self.get_queryset().by_identity(identity)


class HashtagFollow(models.Model):
    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="hashtag_follows",
    )
    hashtag = models.ForeignKey(
        "activities.Hashtag",
        on_delete=models.CASCADE,
        related_name="followers",
        db_index=True,
    )

    created = models.DateTimeField(auto_now_add=True)

    objects = HashtagFollowManager()

    class Meta:
        unique_together = [("identity", "hashtag")]

    def __str__(self):
        return f"#{self.id}: {self.identity} → {self.hashtag_id}"

    ### Alternate fetchers/constructors ###

    @classmethod
    def maybe_get(cls, identity, hashtag) -> Optional["HashtagFollow"]:
        """
        Returns a hashtag follow if it exists between identity and hashtag
        """
        try:
            return HashtagFollow.objects.get(identity=identity, hashtag=hashtag)
        except HashtagFollow.DoesNotExist:
            return None
