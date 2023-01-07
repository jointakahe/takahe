import mimetypes
import re
from functools import partial
from typing import ClassVar

import httpx
import urlman
from asgiref.sync import sync_to_async
from cachetools import TTLCache, cached
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe

from core.files import get_remote_file
from core.html import strip_html
from core.ld import format_ld_date
from core.models import Config
from core.uploads import upload_emoji_namer
from core.uris import (
    AutoAbsoluteUrl,
    ProxyAbsoluteUrl,
    RelativeAbsoluteUrl,
    StaticAbsoluteUrl,
)
from stator.models import State, StateField, StateGraph, StatorModel
from users.models import Domain


class EmojiStates(StateGraph):
    outdated = State(try_interval=300, force_initial=True)
    updated = State()

    outdated.transitions_to(updated)

    @classmethod
    async def handle_outdated(cls, instance: "Emoji"):
        """
        Fetches remote emoji and uploads to file for local caching
        """
        if instance.remote_url and not instance.file:
            try:
                file, mimetype = await get_remote_file(
                    instance.remote_url,
                    timeout=settings.SETUP.REMOTE_TIMEOUT,
                    max_size=settings.SETUP.EMOJI_MAX_IMAGE_FILESIZE_KB * 1024,
                )
            except httpx.RequestError:
                return
            if file:
                instance.file = file
                instance.mimetype = mimetype
                await sync_to_async(instance.save)()

        return cls.updated


class EmojiQuerySet(models.QuerySet):
    def usable(self, domain: Domain | None = None):
        """
        Returns all usable emoji, optionally filtering by domain too.
        """
        visible_q = models.Q(local=True) | models.Q(public=True)
        if Config.system.emoji_unreviewed_are_public:
            visible_q |= models.Q(public__isnull=True)
        qs = self.filter(visible_q)

        if domain:
            if not domain.local:
                qs = qs.filter(domain=domain)

        return qs


class EmojiManager(models.Manager):
    def get_queryset(self):
        return EmojiQuerySet(self.model, using=self._db)

    def usable(self, domain: Domain | None = None):
        return self.get_queryset().usable(domain)


class Emoji(StatorModel):

    # Normalized Emoji without the ':'
    shortcode = models.SlugField(max_length=100, db_index=True)

    domain = models.ForeignKey(
        "users.Domain", null=True, blank=True, on_delete=models.CASCADE
    )
    local = models.BooleanField(default=True)

    # Should this be shown in the public UI?
    public = models.BooleanField(null=True)

    object_uri = models.CharField(max_length=500, blank=True, null=True, unique=True)

    mimetype = models.CharField(max_length=200)

    # Files may not be populated if it's remote and not cached on our side yet
    file = models.ImageField(
        upload_to=partial(upload_emoji_namer, "emoji"),
        null=True,
        blank=True,
    )

    # A link to the custom emoji
    remote_url = models.CharField(max_length=500, blank=True, null=True)

    # Used for sorting custom emoji in the picker
    category = models.CharField(max_length=100, blank=True, null=True)

    # State of this Emoji
    state = StateField(EmojiStates)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = EmojiManager()

    # Cache of the local emojis {shortcode: Emoji}
    locals: ClassVar["dict[str, Emoji]"]

    class Meta:
        unique_together = ("domain", "shortcode")

    class urls(urlman.Urls):
        root = "/admin/emoji/"
        create = "{root}/create/"
        edit = "{root}{self.Emoji}/"
        delete = "{edit}delete/"

    emoji_regex = re.compile(r"\B:([a-zA-Z0-9(_)-]+):\B")

    def clean(self):
        super().clean()
        if self.local ^ (self.domain is None):
            raise ValidationError("Must be local or have a domain")

    def __str__(self):
        return f"{self.id}-{self.shortcode}"

    @classmethod
    def load_locals(cls) -> dict[str, "Emoji"]:
        return {x.shortcode: x for x in Emoji.objects.usable().filter(local=True)}

    @classmethod
    @cached(cache=TTLCache(maxsize=1000, ttl=60))
    def get_by_domain(cls, shortcode, domain: Domain | None) -> "Emoji | None":
        """
        Given an emoji shortcode and optional domain, looks up the single
        emoji and returns it. Raises Emoji.DoesNotExist if there isn't one.
        """
        try:
            if domain is None or domain.local:
                return cls.objects.get(local=True, shortcode=shortcode)
            else:
                return cls.objects.get(domain=domain, shortcode=shortcode)
        except Emoji.DoesNotExist:
            return None

    @property
    def fullcode(self):
        return f":{self.shortcode}:"

    @property
    def is_usable(self) -> bool:
        """
        Return True if this Emoji is usable.
        """
        return self.public or (
            self.public is None and Config.system.emoji_unreviewed_are_public
        )

    def full_url(self) -> RelativeAbsoluteUrl:
        if self.is_usable:
            if self.file:
                return AutoAbsoluteUrl(self.file.url)
            elif self.remote_url:
                return ProxyAbsoluteUrl(
                    f"/proxy/emoji/{self.pk}/",
                    remote_url=self.remote_url,
                )
        return StaticAbsoluteUrl("img/blank-emoji-128.png")

    def as_html(self):
        if self.is_usable:
            return mark_safe(
                f'<img src="{self.full_url().relative}" class="emoji" alt="Emoji {self.shortcode}">'
            )
        return self.fullcode

    @classmethod
    def emojis_from_content(cls, content: str, domain: Domain | None) -> list["Emoji"]:
        """
        Return a parsed and sanitized of emoji found in content without
        the surrounding ':'.
        """
        emoji_hits = cls.emoji_regex.findall(strip_html(content))
        emojis = sorted({emoji.lower() for emoji in emoji_hits})
        return list(
            cls.objects.filter(local=(domain is None) or domain.local)
            .usable(domain)
            .filter(shortcode__in=emojis)
        )

    def to_ap_tag(self):
        """
        Return this Emoji as an ActivityPub Tag
        """
        return {
            "id": self.object_uri or f"https://{settings.MAIN_DOMAIN}/emoji/{self.pk}/",
            "type": "Emoji",
            "name": f":{self.shortcode}:",
            "icon": {
                "type": "Image",
                "mediaType": self.mimetype,
                "url": self.full_url().absolute,
            },
            "updated": format_ld_date(self.updated),
        }

    @classmethod
    def by_ap_tag(cls, domain: Domain, data: dict, create: bool = False):
        """ """
        try:
            return cls.objects.get(object_uri=data["id"])
        except cls.DoesNotExist:
            if not create:
                raise KeyError(f"No emoji with ID {data['id']}", data)

        # Name could be a direct property, or in a language'd value
        if "name" in data:
            name = data["name"]
        elif "nameMap" in data:
            name = data["nameMap"]["und"]
        else:
            raise ValueError("No name on emoji JSON")

        icon = data["icon"]

        mimetype = icon.get("mediaType")
        if not mimetype:
            mimetype, _ = mimetypes.guess_type(icon["url"])
            if mimetype is None:
                raise ValueError("No mimetype on emoji JSON")

        # create
        shortcode = name.lower().strip(":")
        category = (icon.get("category") or "")[:100]

        if not domain.local:
            try:
                emoji = cls.objects.get(shortcode=shortcode, domain=domain)
            except cls.DoesNotExist:
                pass
            else:
                # Domain previously provided this shortcode. Trample in the new emoji
                if emoji.remote_url != icon["url"] or emoji.mimetype != mimetype:
                    emoji.object_uri = data["id"]
                    emoji.remote_url = icon["url"]
                    emoji.mimetype = mimetype
                    emoji.category = category
                    emoji.transition_set_state("outdated")
                    if emoji.file:
                        emoji.file.delete(save=True)
                    else:
                        emoji.save()
                return emoji

        emoji = cls.objects.create(
            shortcode=shortcode,
            domain=None if domain.local else domain,
            local=domain.local,
            object_uri=data["id"],
            mimetype=mimetype,
            category=category,
            remote_url=icon["url"],
        )
        return emoji

    ### Mastodon API ###

    def to_mastodon_json(self):
        url = self.full_url().absolute
        data = {
            "shortcode": self.shortcode,
            "url": url,
            "static_url": self.remote_url or url,
            "visible_in_picker": (
                Config.system.emoji_unreviewed_are_public
                if self.public is None
                else self.public
            ),
            "category": self.category or "",
        }
        return data
