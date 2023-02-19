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

    token = models.CharField(max_length=500, unique=True)
    scopes = models.JSONField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    revoked = models.DateTimeField(blank=True, null=True)

    def has_scope(self, scope: str):
        """
        Returns if this token has the given scope.
        It's a function so we can do mapping/reduction if needed
        """
        # TODO: Support granular scopes the other way?
        scope_prefix = scope.split(":")[0]
        return (scope in self.scopes) or (scope_prefix in self.scopes)
