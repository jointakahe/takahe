from django.db import models


class Block(models.Model):
    """
    When one user (the source) mutes or blocks another (the target)
    """

    source = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="outbound_blocks",
    )

    target = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="inbound_blocks",
    )

    # If it is a mute, we will stop delivering any activities from target to
    # source, but we will still deliver activities from source to target.
    # A full block (non-mute) stops activities both ways.
    mute = models.BooleanField()

    expires = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
