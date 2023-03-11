from django.db import models


class Bookmark(models.Model):
    """
    A (private) bookmark of a Post by an Identity
    """

    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="bookmarks",
    )
    post = models.ForeignKey(
        "activities.Post",
        on_delete=models.CASCADE,
        related_name="bookmarks",
    )

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("identity", "post")]

    def __str__(self):
        return f"#{self.id}: {self.identity} → {self.post}"

    @classmethod
    def for_identity(cls, identity, posts=None, field="id"):
        """
        Returns a set of bookmarked Post IDs for the given identity. If `posts` is
        specified, it is used to filter bookmarks matching those in the list.
        """
        if identity is None:
            return set()
        queryset = cls.objects.filter(identity=identity)
        if posts:
            queryset = queryset.filter(post_id__in=[getattr(p, field) for p in posts])
        return set(queryset.values_list("post_id", flat=True))
