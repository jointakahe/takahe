from django.db import models


class Token(models.Model):
    """
    An (access) token to call the API with.

    Can be either tied to a user, or app-level only.
    """

    application = models.ForeignKey(
        "api.Application",
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    user = models.ForeignKey(
        "users.User",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    identity = models.ForeignKey(
        "users.Identity",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="tokens",
    )

    token = models.CharField(max_length=500)
    code = models.CharField(max_length=100, blank=True, null=True)

    scopes = models.JSONField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
