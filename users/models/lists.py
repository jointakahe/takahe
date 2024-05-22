from django.db import models


class List(models.Model):
    """
    A list of accounts.
    """

    class RepliesPolicy(models.TextChoices):
        followed = "followed"
        list_only = "list"
        none = "none"

    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="lists",
    )
    title = models.CharField(max_length=200)
    replies_policy = models.CharField(max_length=10, choices=RepliesPolicy.choices)
    exclusive = models.BooleanField()
    members = models.ManyToManyField(
        "users.Identity",
        related_name="in_lists",
        blank=True,
    )

    def __str__(self):
        return f"#{self.id}: {self.identity} → {self.title}"

    def to_mastodon_json(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "replies_policy": self.replies_policy,
            "exclusive": self.exclusive,
        }
