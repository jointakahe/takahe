from django.db import models

TokenScope = set[str] | str


def has_required_scopes(scope: TokenScope, *, required: TokenScope) -> bool:
    """
    Returns True if scope contains all required scopes
    """
    if isinstance(scope, str):
        scopes = set(scope.split())
    else:
        scopes = scope
    if isinstance(required, str):
        required_scopes = set(required.split())
    else:
        required_scopes = required or set()
    return (scopes & required_scopes) == required_scopes


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
