from functools import partial
from typing import ClassVar

import pydantic
from django.core.files import File
from django.db import models
from django.templatetags.static import static

from core.uploads import upload_namer
from takahe import __version__


class UploadedImage(str):
    """
    Type used to indicate a setting is an image
    """


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
    image = models.ImageField(
        blank=True,
        null=True,
        upload_to=partial(upload_namer, "config"),
    )

    class Meta:
        unique_together = [
            ("key", "user", "identity"),
        ]

    system: ClassVar["Config.ConfigOptions"]  # type: ignore

    @classmethod
    def load_values(cls, options_class, filters):
        """
        Loads config options and returns an object with them
        """
        values = {}
        for config in cls.objects.filter(**filters):
            values[config.key] = config.image.url if config.image else config.json
            if values[config.key] is None:
                del values[config.key]
        values["version"] = __version__
        return options_class(**values)

    @classmethod
    def load_system(cls):
        """
        Loads the system config options object
        """
        return cls.load_values(
            cls.SystemOptions,
            {"identity__isnull": True, "user__isnull": True},
        )

    @classmethod
    def load_user(cls, user):
        """
        Loads a user config options object
        """
        return cls.load_values(
            cls.SystemOptions,
            {"identity__isnull": True, "user": user},
        )

    @classmethod
    def load_identity(cls, identity):
        """
        Loads a user config options object
        """
        return cls.load_values(
            cls.IdentityOptions,
            {"identity": identity, "user__isnull": True},
        )

    @classmethod
    def set_value(cls, key, value, options_class, filters):
        config_field = options_class.__fields__[key]
        if isinstance(value, File):
            if config_field.type_ is not UploadedImage:
                raise ValueError(f"Cannot save file to {key} of type: {type(value)}")
            cls.objects.update_or_create(
                key=key,
                defaults={"json": None, "image": value},
                **filters,
            )
        elif value is None:
            cls.objects.filter(key=key, **filters).delete()
        else:
            if not isinstance(value, config_field.type_):
                raise ValueError(f"Invalid type for {key}: {type(value)}")
            if value == config_field.default:
                cls.objects.filter(key=key, **filters).delete()
            else:
                cls.objects.update_or_create(
                    key=key,
                    defaults={"json": value},
                    **filters,
                )

    @classmethod
    def set_system(cls, key, value):
        cls.set_value(
            key,
            value,
            cls.SystemOptions,
            {"identity__isnull": True, "user__isnull": True},
        )

    @classmethod
    def set_user(cls, user, key, value):
        cls.set_value(
            key,
            value,
            cls.UserOptions,
            {"identity__isnull": True, "user": user},
        )

    @classmethod
    def set_identity(cls, identity, key, value):
        cls.set_value(
            key,
            value,
            cls.IdentityOptions,
            {"identity": identity, "user__isnull": True},
        )

    class SystemOptions(pydantic.BaseModel):

        version: str = __version__

        system_actor_public_key: str = ""
        system_actor_private_key: str = ""

        site_name: str = "Takahē"
        highlight_color: str = "#449c8c"
        site_about: str = "<h2>Welcome!</h2>\n\nThis is a community running Takahē."
        site_icon: UploadedImage = static("img/icon-128.png")
        site_banner: UploadedImage = static("img/fjords-banner-600.jpg")

        signup_allowed: bool = True
        signup_invite_only: bool = False
        signup_text: str = ""

        post_length: int = 500
        identity_min_length: int = 2
        identity_max_per_user: int = 5
        identity_max_age: int = 24 * 60 * 60

        restricted_usernames: str = "admin\nadmins\nadministrator\nadministrators\nsystem\nroot\nannounce\nannouncement\nannouncements"

    class UserOptions(pydantic.BaseModel):

        pass

    class IdentityOptions(pydantic.BaseModel):

        toot_mode: bool = False
