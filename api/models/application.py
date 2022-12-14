from django.db import models


class Application(models.Model):
    """
    OAuth applications
    """

    client_id = models.CharField(max_length=500)
    client_secret = models.CharField(max_length=500)

    redirect_uris = models.TextField()
    scopes = models.TextField()

    name = models.CharField(max_length=500)
    website = models.CharField(max_length=500, blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def is_scope_subset(self, scopes: str) -> bool:
        """
        Return True if the scopes are a subset of this Application's scopes
        """
        app_scopes = set(filter(None, (self.scopes or "read").split()))
        other_scopes = set(filter(None, scopes.split()))

        return app_scopes & other_scopes == other_scopes
