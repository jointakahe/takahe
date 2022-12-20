import random

import urlman
from django.db import models


class Invite(models.Model):
    """
    An invite token, good for one signup.
    """

    # Should always be lowercase
    token = models.CharField(max_length=500, unique=True)

    # Is it limited to a specific email?
    email = models.EmailField(null=True, blank=True)

    # Admin note about this code
    note = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class urls(urlman.Urls):
        admin = "/admin/invites/"
        admin_create = "{admin}create/"
        admin_view = "{admin}{self.pk}/"

    @classmethod
    def create_random(cls, email=None):
        return cls.objects.create(
            token="".join(
                random.choice("abcdefghkmnpqrstuvwxyz23456789") for i in range(20)
            ),
            email=email,
        )
