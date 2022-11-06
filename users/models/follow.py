from django.db import models


class Follow(models.Model):
    """
    When one user (the source) follows other (the target)
    """

    source = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="outbound_follows",
    )
    target = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="inbound_follows",
    )

    note = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
