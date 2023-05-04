from functools import partial
from typing import ClassVar

import pydantic
from asgiref.sync import sync_to_async
from django.core.files import File
from django.db import models
from django.utils.functional import lazy

from core.uploads import upload_namer
from core.uris import StaticAbsoluteUrl
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

    domain = models.ForeignKey(
        "users.domain",
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
            ("key", "user", "identity", "domain"),
        ]

    system: ClassVar["Config.ConfigOptions"]  # type: ignore

    @classmethod
    def lazy_system_value(cls, key: str):
        """
        Lazily load a System.Config value
        """
        if key not in cls.SystemOptions.__fields__:
            raise KeyError(f"Undefined SystemOption for {key}")
        return lazy(lambda: getattr(Config.system, key))

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
            {"identity__isnull": True, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    async def aload_system(cls):
        """
        Async loads the system config options object
        """
        return await sync_to_async(cls.load_values)(
            cls.SystemOptions,
            {"identity__isnull": True, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    def load_user(cls, user):
        """
        Loads a user config options object
        """
        return cls.load_values(
            cls.UserOptions,
            {"identity__isnull": True, "user": user, "domain__isnull": True},
        )

    @classmethod
    async def aload_user(cls, user):
        """
        Async loads the user config options object
        """
        return await sync_to_async(cls.load_values)(
            cls.UserOptions,
            {"identity__isnull": True, "user": user, "domain__isnull": True},
        )

    @classmethod
    def load_identity(cls, identity):
        """
        Loads an identity config options object
        """
        return cls.load_values(
            cls.IdentityOptions,
            {"identity": identity, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    async def aload_identity(cls, identity):
        """
        Async loads an identity config options object
        """
        return await sync_to_async(cls.load_values)(
            cls.IdentityOptions,
            {"identity": identity, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    def load_domain(cls, domain):
        """
        Loads an domain config options object
        """
        return cls.load_values(
            cls.DomainOptions,
            {"domain": domain, "user__isnull": True, "identity__isnull": True},
        )

    @classmethod
    async def aload_domain(cls, domain):
        """
        Async loads an domain config options object
        """
        return await sync_to_async(cls.load_values)(
            cls.DomainOptions,
            {"domain": domain, "user__isnull": True, "identity__isnull": True},
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
            {"identity__isnull": True, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    def set_user(cls, user, key, value):
        cls.set_value(
            key,
            value,
            cls.UserOptions,
            {"identity__isnull": True, "user": user, "domain__isnull": True},
        )

    @classmethod
    def set_identity(cls, identity, key, value):
        cls.set_value(
            key,
            value,
            cls.IdentityOptions,
            {"identity": identity, "user__isnull": True, "domain__isnull": True},
        )

    @classmethod
    def set_domain(cls, domain, key, value):
        cls.set_value(
            key,
            value,
            cls.DomainOptions,
            {"domain": domain, "user__isnull": True, "identity__isnull": True},
        )

    class SystemOptions(pydantic.BaseModel):

        version: str = __version__

        system_actor_public_key: str = ""
        system_actor_private_key: str = ""

        site_name: str = "Takahē"
        highlight_color: str = "#449c8c"
        site_about: str = "<h2>Welcome!</h2>\n\nThis is a community running Takahē."
        site_frontpage_posts: bool = True
        site_icon: UploadedImage = StaticAbsoluteUrl("img/icon-128.png").relative  # type: ignore
        site_banner: UploadedImage = StaticAbsoluteUrl(
            "img/fjords-banner-600.jpg"
        ).relative  # type: ignore

        policy_terms: str = ""
        policy_privacy: str = ""
        policy_rules: str = ""
        policy_issues: str = ""

        signup_allowed: bool = True
        signup_text: str = ""
        signup_max_users: int = 0
        signup_email_admins: bool = True
        content_warning_text: str = "Content Warning"

        post_length: int = 500
        post_minimum_interval: int = 3  # seconds
        identity_min_length: int = 2
        identity_max_per_user: int = 5
        identity_max_age: int = 24 * 60 * 60
        public_timeline: bool = True

        hashtag_unreviewed_are_public: bool = True
        hashtag_stats_max_age: int = 60 * 60

        emoji_unreviewed_are_public: bool = True

        cache_timeout_page_default: int = 60
        cache_timeout_page_timeline: int = 60 * 3
        cache_timeout_page_post: int = 60 * 2
        cache_timeout_identity_feed: int = 60 * 5

        restricted_usernames: str = "admin\nadmins\nadministrator\nadministrators\nsystem\nroot\nannounce\nannouncement\nannouncements"

        custom_head: str | None

    class UserOptions(pydantic.BaseModel):
        light_theme: bool = False

    class IdentityOptions(pydantic.BaseModel):

        toot_mode: bool = False
        default_post_visibility: int = 0  # Post.Visibilities.public
        visible_follows: bool = True
        search_enabled: bool = True

        # Wellness Options
        visible_reaction_counts: bool = True
        expand_linked_cws: bool = True

    class DomainOptions(pydantic.BaseModel):

        site_name: str = ""
        site_icon: UploadedImage | None = None
        hide_login: bool = False
        custom_css: str = ""
        single_user: str = ""
