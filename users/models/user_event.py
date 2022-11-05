from django.db import models


class UserEvent(models.Model):
    """
    Tracks major events that happen to users
    """

    class EventType(models.TextChoices):
        created = "created"
        reset_password = "reset_password"
        banned = "banned"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="events",
    )

    date = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=100, choices=EventType.choices)
    data = models.JSONField(blank=True, null=True)
