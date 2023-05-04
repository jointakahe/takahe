import secrets

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

    @classmethod
    def create(
        cls,
        client_name: str,
        redirect_uris: str,
        website: str | None,
        scopes: str | None = None,
    ):
        client_id = "tk-" + secrets.token_urlsafe(16)
        client_secret = secrets.token_urlsafe(40)

        return cls.objects.create(
            name=client_name,
            website=website,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=redirect_uris,
            scopes=scopes or "read",
        )
