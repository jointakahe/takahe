from typing import ClassVar

import pydantic
from django.db import models
from django.utils.functional import classproperty


class Config(models.Model):
    """
    A configuration setting for either the server or a specific user or identity.

    The possible options and their defaults are defined at the bottom of the file.
    """

    key = models.CharField(max_length=500)

    user = models.ForeignKey(
        "users.user",
        blank=True,
        null=True,
        related_name="configs",
        on_delete=models.CASCADE,
    )

    identity = models.ForeignKey(
        "users.identity",
        blank=True,
        null=True,
        related_name="configs",
        on_delete=models.CASCADE,
    )

    json = models.JSONField(blank=True, null=True)
    image = models.ImageField(blank=True, null=True, upload_to="config/%Y/%m/%d/")

    class Meta:
        unique_together = [
            ("key", "user", "identity"),
        ]

    @classproperty
    def system(cls):
        cls.system = cls.load_system()
        return cls.system

    system: ClassVar["Config.ConfigOptions"]  # type: ignore

    @classmethod
    def load_system(cls):
        """
        Load all of the system config options and return an object with them
        """
        values = {}
        for config in cls.objects.filter(user__isnull=True, identity__isnull=True):
            values[config.key] = config.image or config.json
        return cls.SystemOptions(**values)

    @classmethod
    def load_user(cls, user):
        """
        Load all of the user config options and return an object with them
        """
        values = {}
        for config in cls.objects.filter(user=user, identity__isnull=True):
            values[config.key] = config.image or config.json
        return cls.UserOptions(**values)

    @classmethod
    def load_identity(cls, identity):
        """
        Load all of the identity config options and return an object with them
        """
        values = {}
        for config in cls.objects.filter(user__isnull=True, identity=identity):
            values[config.key] = config.image or config.json
        return cls.IdentityOptions(**values)

    @classmethod
    def set_system(cls, key, value):
        config_field = cls.SystemOptions.__fields__[key]
        if not isinstance(value, config_field.type_):
            raise ValueError(f"Invalid type for {key}: {type(value)}")
        cls.objects.update_or_create(
            key=key,
            defaults={"json": value},
        )

    @classmethod
    def set_identity(cls, identity, key, value):
        config_field = cls.IdentityOptions.__fields__[key]
        if not isinstance(value, config_field.type_):
            raise ValueError(f"Invalid type for {key}: {type(value)}")
        cls.objects.update_or_create(
            identity=identity,
            key=key,
            defaults={"json": value},
        )

    class SystemOptions(pydantic.BaseModel):

        site_name: str = "takahē"
        highlight_color: str = "#449c8c"
        identity_max_age: int = 24 * 60 * 60

    class UserOptions(pydantic.BaseModel):

        pass

    class IdentityOptions(pydantic.BaseModel):

        toot_mode: bool = False
