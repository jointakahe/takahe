from functools import cached_property, partial
from typing import Literal
from urllib.parse import urlparse

import httpx
import urlman
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.db import IntegrityError, models
from django.template.defaultfilters import linebreaks_filter
from django.utils import timezone
from django.utils.functional import lazy

from core.exceptions import ActorMismatchError
from core.files import get_remote_file
from core.html import sanitize_post, strip_html
from core.ld import canonicalise, format_ld_date, get_list, media_type_from_filename
from core.models import Config
from core.signatures import HttpSignature, RsaKeys
from core.uploads import upload_namer
from core.uris import AutoAbsoluteUrl, RelativeAbsoluteUrl, StaticAbsoluteUrl
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.domain import Domain
from users.models.system_actor import SystemActor


class IdentityStates(StateGraph):
    """
    There are only two states in a cycle.
    Identities sit in "updated" for up to system.identity_max_age, and then
    go back to "outdated" for refetching.
    """

    outdated = State(try_interval=3600, force_initial=True)
    updated = State(try_interval=86400 * 7, attempt_immediately=False)

    outdated.transitions_to(updated)
    updated.transitions_to(outdated)

    @classmethod
    async def handle_outdated(cls, identity: "Identity"):
        # Local identities never need fetching
        if identity.local:
            return cls.updated
        # Run the actor fetch and progress to updated if it succeeds
        if await identity.fetch_actor():
            # Also stash their icon if we can
            if identity.icon_uri:
                try:
                    file, mimetype = await get_remote_file(
                        identity.icon_uri,
                        timeout=settings.SETUP.REMOTE_TIMEOUT,
                        max_size=settings.SETUP.AVATAR_MAX_IMAGE_FILESIZE_KB * 1024,
                    )
                except httpx.RequestError:
                    # We've still got enough info to consider ourselves updated
                    return cls.updated
                if file:
                    identity.icon = file
                    await sync_to_async(identity.save)()
            return cls.updated

    @classmethod
    async def handle_updated(cls, instance: "Identity"):
        if instance.state_age > Config.system.identity_max_age:
            return cls.outdated


class Identity(StatorModel):
    """
    Represents both local and remote Fediverse identities (actors)
    """

    class Restriction(models.IntegerChoices):
        none = 0
        limited = 1
        blocked = 2

    # The Actor URI is essentially also a PK - we keep the default numeric
    # one around as well for making nice URLs etc.
    actor_uri = models.CharField(max_length=500, unique=True)

    state = StateField(IdentityStates)

    local = models.BooleanField()
    users = models.ManyToManyField(
        "users.User",
        related_name="identities",
        blank=True,
    )

    username = models.CharField(max_length=500, blank=True, null=True)
    # Must be a display domain if present
    domain = models.ForeignKey(
        "users.Domain",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="identities",
    )

    name = models.CharField(max_length=500, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    manually_approves_followers = models.BooleanField(blank=True, null=True)
    discoverable = models.BooleanField(default=True)

    profile_uri = models.CharField(max_length=500, blank=True, null=True)
    inbox_uri = models.CharField(max_length=500, blank=True, null=True)
    shared_inbox_uri = models.CharField(max_length=500, blank=True, null=True)
    outbox_uri = models.CharField(max_length=500, blank=True, null=True)
    icon_uri = models.CharField(max_length=500, blank=True, null=True)
    image_uri = models.CharField(max_length=500, blank=True, null=True)
    followers_uri = models.CharField(max_length=500, blank=True, null=True)
    following_uri = models.CharField(max_length=500, blank=True, null=True)

    icon = models.ImageField(
        upload_to=partial(upload_namer, "profile_images"), blank=True, null=True
    )
    image = models.ImageField(
        upload_to=partial(upload_namer, "background_images"), blank=True, null=True
    )

    # Should be a list of {"name":..., "value":...} dicts
    metadata = models.JSONField(blank=True, null=True)

    # Should be a list of object URIs (we don't want a full M2M here)
    pinned = models.JSONField(blank=True, null=True)

    # Admin-only moderation fields
    sensitive = models.BooleanField(default=False)
    restriction = models.IntegerField(
        choices=Restriction.choices, default=Restriction.none
    )
    admin_notes = models.TextField(null=True, blank=True)

    private_key = models.TextField(null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)
    public_key_id = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    fetched = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)

    ### Model attributes ###

    class Meta:
        verbose_name_plural = "identities"
        unique_together = [("username", "domain")]

    class urls(urlman.Urls):
        view = "/@{self.username}@{self.domain_id}/"
        action = "{view}action/"
        activate = "{view}activate/"
        admin = "/admin/identities/"
        admin_edit = "{admin}{self.pk}/"

        def get_scheme(self, url):
            return "https"

        def get_hostname(self, url):
            return self.instance.domain.uri_domain

    def __str__(self):
        if self.username and self.domain_id:
            return self.handle
        return self.actor_uri

    def absolute_profile_uri(self):
        """
        Returns a profile URI that is always absolute, for sending out to
        other servers.
        """
        if self.local:
            return f"https://{self.domain.uri_domain}/@{self.username}/"
        else:
            return self.profile_uri

    def local_icon_url(self) -> RelativeAbsoluteUrl:
        """
        Returns an icon for use by us, with fallbacks to a placeholder
        """
        if self.icon:
            return RelativeAbsoluteUrl(self.icon.url)
        elif self.icon_uri:
            return AutoAbsoluteUrl(f"/proxy/identity_icon/{self.pk}/")
        else:
            return StaticAbsoluteUrl("img/unknown-icon-128.png")

    def local_image_url(self) -> RelativeAbsoluteUrl | None:
        """
        Returns a background image for us, returning None if there isn't one
        """
        if self.image:
            return RelativeAbsoluteUrl(self.image.url)
        elif self.image_uri:
            return AutoAbsoluteUrl(f"/proxy/identity_image/{self.pk}/")
        return None

    @property
    def safe_summary(self):
        from activities.templatetags.emoji_tags import imageify_emojis

        return imageify_emojis(sanitize_post(self.summary), self.domain)

    @property
    def safe_metadata(self):
        from activities.templatetags.emoji_tags import imageify_emojis

        if not self.metadata:
            return []
        return [
            {
                "name": data["name"],
                "value": imageify_emojis(strip_html(data["value"]), self.domain),
            }
            for data in self.metadata
        ]

    ### Alternate constructors/fetchers ###

    @classmethod
    def by_username_and_domain(cls, username, domain, fetch=False, local=False):
        if username.startswith("@"):
            raise ValueError("Username must not start with @")
        username = username.lower()
        domain = domain.lower()
        try:
            if local:
                return cls.objects.get(
                    username=username,
                    domain_id=domain,
                    local=True,
                )
            else:
                return cls.objects.get(
                    username=username,
                    domain_id=domain,
                )
        except cls.DoesNotExist:
            if fetch and not local:
                actor_uri, handle = async_to_sync(cls.fetch_webfinger)(
                    f"{username}@{domain}"
                )
                if handle is None:
                    return None
                # See if this actually does match an existing actor
                try:
                    return cls.objects.get(actor_uri=actor_uri)
                except cls.DoesNotExist:
                    pass
                # OK, make one
                username, domain = handle.split("@")
                domain = Domain.get_remote_domain(domain)
                return cls.objects.create(
                    actor_uri=actor_uri,
                    username=username,
                    domain_id=domain,
                    local=False,
                )
            return None

    @classmethod
    def by_actor_uri(cls, uri, create=False, transient=False) -> "Identity":
        try:
            return cls.objects.get(actor_uri=uri)
        except cls.DoesNotExist:
            if create:
                if transient:
                    # Some code (like inbox fetching) doesn't need this saved
                    # to the DB until the fetch succeeds
                    return cls(actor_uri=uri, local=False)
                else:
                    return cls.objects.create(actor_uri=uri, local=False)
            else:
                raise cls.DoesNotExist(f"No identity found with actor_uri {uri}")

    ### Dynamic properties ###

    @property
    def name_or_handle(self):
        return self.name or self.handle

    @cached_property
    def html_name_or_handle(self):
        """
        Return the name_or_handle with any HTML substitutions made
        """
        from activities.templatetags.emoji_tags import imageify_emojis

        return imageify_emojis(self.name_or_handle, self.domain)

    @property
    def handle(self):
        if self.username is None:
            return "(unknown user)"
        if self.domain_id:
            return f"{self.username}@{self.domain_id}"
        return f"{self.username}@(unknown server)"

    @property
    def data_age(self) -> float:
        """
        How old our copy of this data is, in seconds
        """
        if self.local:
            return 0
        if self.fetched is None:
            return 10000000000
        return (timezone.now() - self.fetched).total_seconds()

    @property
    def outdated(self) -> bool:
        # TODO: Setting
        return self.data_age > 60 * 24 * 24

    @property
    def blocked(self) -> bool:
        return self.restriction == self.Restriction.blocked

    @property
    def limited(self) -> bool:
        return self.restriction == self.Restriction.limited

    ### ActivityPub (outbound) ###

    def to_ap(self):
        response = {
            "id": self.actor_uri,
            "type": "Person",
            "inbox": self.actor_uri + "inbox/",
            "preferredUsername": self.username,
            "publicKey": {
                "id": self.public_key_id,
                "owner": self.actor_uri,
                "publicKeyPem": self.public_key,
            },
            "published": self.created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": self.absolute_profile_uri(),
            "toot:discoverable": self.discoverable,
        }
        if self.name:
            response["name"] = self.name
        if self.summary:
            response["summary"] = str(linebreaks_filter(self.summary))
        if self.icon:
            response["icon"] = {
                "type": "Image",
                "mediaType": media_type_from_filename(self.icon.name),
                "url": self.icon.url,
            }
        if self.image:
            response["image"] = {
                "type": "Image",
                "mediaType": media_type_from_filename(self.image.name),
                "url": self.image.url,
            }
        if self.local:
            response["endpoints"] = {
                "sharedInbox": f"https://{self.domain.uri_domain}/inbox/",
            }
        return response

    def to_ap_tag(self):
        """
        Return this Identity as an ActivityPub Tag
        """
        return {
            "href": self.actor_uri,
            "name": "@" + self.handle,
            "type": "Mention",
        }

    ### ActivityPub (inbound) ###

    @classmethod
    def handle_update_ap(cls, data):
        """
        Takes an incoming update.person message and just forces us to add it
        to our fetch queue (don't want to bother with two load paths right now)
        """
        # Find by actor
        try:
            actor = cls.by_actor_uri(data["actor"])
            actor.transition_perform(IdentityStates.outdated)
        except cls.DoesNotExist:
            pass

    @classmethod
    def handle_delete_ap(cls, data):
        """
        Takes an incoming update.person message and just forces us to add it
        to our fetch queue (don't want to bother with two load paths right now)
        """
        # Assert that the actor matches the object
        if data["actor"] != data["object"]:
            raise ActorMismatchError(
                f"Actor {data['actor']} trying to delete identity {data['object']}"
            )
        # Find by actor
        try:
            actor = cls.by_actor_uri(data["actor"])
            actor.delete()
        except cls.DoesNotExist:
            pass

    ### Actor/Webfinger fetching ###

    @classmethod
    async def fetch_webfinger(cls, handle: str) -> tuple[str | None, str | None]:
        """
        Given a username@domain handle, returns a tuple of
        (actor uri, canonical handle) or None, None if it does not resolve.
        """
        domain = handle.split("@")[1].lower()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://{domain}/.well-known/webfinger?resource=acct:{handle}",
                )
        except httpx.RequestError:
            return None, None
        if response.status_code in [404, 410]:
            return None, None
        if response.status_code >= 500:
            return None, None
        if response.status_code >= 400:
            raise ValueError(
                f"Client error fetching webfinger: {response.status_code}",
                response.content,
            )
        data = response.json()
        if data["subject"].startswith("acct:"):
            data["subject"] = data["subject"][5:]
        for link in data["links"]:
            if (
                link.get("type") == "application/activity+json"
                and link.get("rel") == "self"
            ):
                return link["href"], data["subject"]
        return None, None

    async def fetch_actor(self) -> bool:
        """
        Fetches the user's actor information, as well as their domain from
        webfinger if it's available.
        """
        from activities.models import Emoji

        if self.local:
            raise ValueError("Cannot fetch local identities")
        try:
            response = await SystemActor().signed_request(
                method="get",
                uri=self.actor_uri,
            )
        except httpx.RequestError:
            return False
        if response.status_code == 410:
            # Their account got deleted, so let's do the same.
            if self.pk:
                await Identity.objects.filter(pk=self.pk).adelete()
            return False
        if response.status_code == 404:
            # We don't trust this as much as 410 Gone, but skip for now
            return False
        if response.status_code >= 500:
            return False
        if response.status_code >= 400:
            raise ValueError(
                f"Client error fetching actor: {response.status_code}", response.content
            )
        document = canonicalise(response.json(), include_security=True)
        self.name = document.get("name")
        self.profile_uri = document.get("url")
        self.inbox_uri = document.get("inbox")
        self.outbox_uri = document.get("outbox")
        self.followers_uri = document.get("followers")
        self.following_uri = document.get("following")
        self.shared_inbox_uri = document.get("endpoints", {}).get("sharedInbox")
        self.summary = document.get("summary")
        self.username = document.get("preferredUsername")
        if self.username and "@value" in self.username:
            self.username = self.username["@value"]
        if self.username:
            self.username = self.username.lower()
        self.manually_approves_followers = document.get("manuallyApprovesFollowers")
        self.public_key = document.get("publicKey", {}).get("publicKeyPem")
        self.public_key_id = document.get("publicKey", {}).get("id")
        self.icon_uri = document.get("icon", {}).get("url")
        self.image_uri = document.get("image", {}).get("url")
        self.discoverable = document.get("toot:discoverable", True)
        # Profile links/metadata
        self.metadata = []
        for attachment in get_list(document, "attachment"):
            if (
                attachment["type"] == "http://schema.org#PropertyValue"
                and "name" in attachment
                and "http://schema.org#value" in attachment
            ):
                self.metadata.append(
                    {
                        "name": attachment.get("name"),
                        "value": strip_html(attachment.get("http://schema.org#value")),
                    }
                )
        # Now go do webfinger with that info to see if we can get a canonical domain
        actor_url_parts = urlparse(self.actor_uri)
        get_domain = sync_to_async(Domain.get_remote_domain)
        if self.username:
            webfinger_actor, webfinger_handle = await self.fetch_webfinger(
                f"{self.username}@{actor_url_parts.hostname}"
            )
            if webfinger_handle:
                webfinger_username, webfinger_domain = webfinger_handle.split("@")
                self.username = webfinger_username.lower()
                self.domain = await get_domain(webfinger_domain)
            else:
                self.domain = await get_domain(actor_url_parts.hostname)
        else:
            self.domain = await get_domain(actor_url_parts.hostname)
        # Emojis (we need the domain so we do them here)
        for tag in get_list(document, "tag"):
            if tag["type"].lower() == "toot:emoji":
                await sync_to_async(Emoji.by_ap_tag)(self.domain, tag, create=True)
        # Mark as fetched
        self.fetched = timezone.now()
        try:
            await sync_to_async(self.save)()
        except IntegrityError as e:
            # See if we can fetch a PK and save there
            if self.pk is None:
                try:
                    other_row = await Identity.objects.aget(actor_uri=self.actor_uri)
                except Identity.DoesNotExist:
                    raise ValueError(
                        f"Could not save Identity at end of actor fetch: {e}"
                    )
                self.pk: int | None = other_row.pk
                await sync_to_async(self.save)()
        return True

    ### Mastodon Client API ###

    def to_mastodon_json(self):
        from activities.models import Emoji

        header_image = self.local_image_url()
        metadata_value_text = (
            " ".join([m["value"] for m in self.metadata]) if self.metadata else ""
        )
        emojis = Emoji.emojis_from_content(
            f"{self.name} {self.summary} {metadata_value_text}", self.domain
        )
        return {
            "id": self.pk,
            "username": self.username or "",
            "acct": self.username if self.local else self.handle,
            "url": self.absolute_profile_uri() or "",
            "display_name": self.name or "",
            "note": self.summary or "",
            "avatar": self.local_icon_url().absolute,
            "avatar_static": self.local_icon_url().absolute,
            "header": header_image.absolute if header_image else None,
            "header_static": header_image.absolute if header_image else None,
            "locked": False,
            "fields": (
                [
                    {"name": m["name"], "value": m["value"], "verified_at": None}
                    for m in self.metadata
                ]
                if self.metadata
                else []
            ),
            "emojis": [emoji.to_mastodon_json() for emoji in emojis],
            "bot": False,
            "group": False,
            "discoverable": self.discoverable,
            "suspended": False,
            "limited": False,
            "created_at": format_ld_date(
                self.created.replace(hour=0, minute=0, second=0, microsecond=0)
            ),
            "last_status_at": None,  # TODO: populate
            "statuses_count": self.posts.count(),
            "followers_count": self.inbound_follows.count(),
            "following_count": self.outbound_follows.count(),
        }

    ### Cryptography ###

    async def signed_request(
        self,
        method: Literal["get", "post"],
        uri: str,
        body: dict | None = None,
    ):
        """
        Performs a signed request on behalf of the System Actor.
        """
        return await HttpSignature.signed_request(
            method=method,
            uri=uri,
            body=body,
            private_key=self.private_key,
            key_id=self.public_key_id,
        )

    def generate_keypair(self):
        if not self.local:
            raise ValueError("Cannot generate keypair for remote user")
        self.private_key, self.public_key = RsaKeys.generate_keypair()
        self.public_key_id = self.actor_uri + "#main-key"
        self.save()

    ### Config ###

    @cached_property
    def config_identity(self) -> Config.IdentityOptions:
        return Config.load_identity(self)

    def lazy_config_value(self, key: str):
        """
        Lazily load a config value for this Identity
        """
        if key not in Config.IdentityOptions.__fields__:
            raise KeyError(f"Undefined IdentityOption for {key}")
        return lazy(lambda: getattr(self.config_identity, key))
