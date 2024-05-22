from django.db import models

from core.ld import format_ld_date


class Marker(models.Model):
    """
    A timeline marker.
    """

    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="markers",
    )
    timeline = models.CharField(max_length=100)
    last_read_id = models.CharField(max_length=200)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("identity", "timeline")]

    def __str__(self):
        return f"#{self.id}: {self.identity} → {self.timeline}[{self.last_read_id}]"

    def to_mastodon_json(self):
        return {
            "last_read_id": self.last_read_id,
            "version": 0,
            "updated_at": format_ld_date(self.updated_at),
        }
