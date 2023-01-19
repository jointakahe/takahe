from django.db import models


class Authorization(models.Model):
    """
    An authorization code as part of the OAuth flow
    """

    application = models.ForeignKey(
        "api.Application",
        on_delete=models.CASCADE,
        related_name="authorizations",
    )

    user = models.ForeignKey(
        "users.User",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="authorizations",
    )

    identity = models.ForeignKey(
        "users.Identity",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="authorizations",
    )

    code = models.CharField(max_length=128, blank=True, null=True, unique=True)
    token = models.OneToOneField(
        "api.Token",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    scopes = models.JSONField()
    redirect_uri = models.TextField(blank=True, null=True)
    valid_for_seconds = models.IntegerField(default=60)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
