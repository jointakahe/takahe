import random

import urlman
from django.db import models
from django.utils import timezone


class Invite(models.Model):
    """
    An invite token, good for one signup.
    """

    # Should always be lowercase
    token = models.CharField(max_length=500, unique=True)

    # Admin note about this code
    note = models.TextField(null=True, blank=True)

    # Uses remaining (null means "infinite")
    uses = models.IntegerField(null=True, blank=True)

    # Expiry date
    expires = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class urls(urlman.Urls):
        admin = "/admin/invites/"
        admin_create = "{admin}create/"
        admin_view = "{admin}{self.pk}/"

    @classmethod
    def create_random(cls, uses=None, expires=None, note=None):
        return cls.objects.create(
            token="".join(
                random.choice("abcdefghkmnpqrstuvwxyz23456789") for i in range(20)
            ),
            uses=uses,
            expires=expires,
            note=note,
        )

    @property
    def valid(self):
        if self.uses is not None:
            if self.uses <= 0:
                return False
        if self.expires is not None:
            return self.expires >= timezone.now()
        return True
