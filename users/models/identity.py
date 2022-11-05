import base64
import uuid
from functools import partial

import urlman
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.db import models
from django.utils import timezone


def upload_namer(prefix, instance, filename):
    """
    Names uploaded images etc.
    """
    now = timezone.now()
    filename = base64.b32encode(uuid.uuid4().bytes).decode("ascii")
    return f"{prefix}/{now.year}/{now.month}/{now.day}/{filename}"


class Identity(models.Model):
    """
    Represents both local and remote Fediverse identities (actors)
    """

    # The handle includes the domain!
    handle = models.CharField(max_length=500, unique=True)
    name = models.CharField(max_length=500, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    profile_image = models.ImageField(upload_to=partial(upload_namer, "profile_images"))
    background_image = models.ImageField(
        upload_to=partial(upload_namer, "background_images")
    )

    local = models.BooleanField()
    users = models.ManyToManyField("users.User", related_name="identities")
    private_key = models.TextField(null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.DateTimeField(null=True, blank=True)

    @property
    def short_handle(self):
        if self.handle.endswith("@" + settings.DEFAULT_DOMAIN):
            return self.handle.split("@", 1)[0]
        return self.handle

    @property
    def domain(self):
        return self.handle.split("@", 1)[1]

    def generate_keypair(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.private_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.save()

    def __str__(self):
        return self.name or self.handle

    class urls(urlman.Urls):
        view = "/@{self.short_handle}/"
        actor = "{view}actor/"
        inbox = "{actor}inbox/"
        activate = "{view}activate/"
