from django.db import models


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
    )

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("identity", "hashtag")]

    def __str__(self):
        return f"#{self.id}: {self.identity} → {self.hashtag_id}"
