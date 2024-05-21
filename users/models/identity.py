import logging
import ssl
from functools import cached_property, partial
from typing import Literal, Optional
from urllib.parse import urlparse

import httpx
import urlman
from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.functional import lazy
from lxml import etree

from core.exceptions import ActorMismatchError
from core.html import ContentRenderer, FediverseHtmlParser
from core.json import json_from_response
from core.ld import (
    canonicalise,
    format_ld_date,
    get_first_image_url,
    get_list,
    media_type_from_filename,
)
from core.models import Config
from core.signatures import HttpSignature, RsaKeys
from core.snowflake import Snowflake
from core.uploads import upload_namer
from core.uris import (
    AutoAbsoluteUrl,
    ProxyAbsoluteUrl,
    RelativeAbsoluteUrl,
    StaticAbsoluteUrl,
)
from stator.exceptions import TryAgainLater
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.domain import Domain
from users.models.inbox_message import InboxMessage
from users.models.system_actor import SystemActor

logger = logging.getLogger(__name__)


class IdentityStates(StateGraph):
    """
    Identities sit in "updated" for up to system.identity_max_age, and then
    go back to "outdated" for refetching.

    When a local identity is "edited" or "deleted", it will fanout the change to
    all followers and transition to "updated"
    """

    outdated = State(try_interval=3600, force_initial=True)
    updated = State(try_interval=86400 * 15, attempt_immediately=False)

    edited = State(try_interval=300, attempt_immediately=True)
    deleted = State(try_interval=300, attempt_immediately=True)
    deleted_fanned_out = State(delete_after=86400 * 7)

    moved = State(try_interval=300, attempt_immediately=True)
    moved_fanned_out = State(externally_progressed=True)

    deleted.transitions_to(deleted_fanned_out)

    edited.transitions_to(updated)
    updated.transitions_to(edited)
    edited.transitions_to(deleted)

    outdated.transitions_to(updated)
    updated.transitions_to(outdated)

    updated.transitions_to(moved)
    moved.transitions_to(moved_fanned_out)

    @classmethod
    def group_deleted(cls):
        return [cls.deleted, cls.deleted_fanned_out]

    @classmethod
    def targets_fan_out(cls, identity: "Identity", type_: str) -> None:
        from activities.models import FanOut
        from users.models import Follow

        # Fan out to each target
        shared_inboxes = set()
        for follower in Follow.objects.select_related("source", "target").filter(
            target=identity
        ):
            # Dedupe shared_inbox_uri
            shared_uri = follower.source.shared_inbox_uri
            if shared_uri and shared_uri in shared_inboxes:
                continue

            FanOut.objects.create(
                identity=follower.source,
                type=type_,
                subject_identity=identity,
            )
            shared_inboxes.add(shared_uri)

    @classmethod
    def handle_edited(cls, instance: "Identity"):
        from activities.models import FanOut

        if not instance.local:
            return cls.updated

        cls.targets_fan_out(instance, FanOut.Types.identity_edited)
        return cls.updated

    @classmethod
    def handle_moved(cls, instance: "Identity"):
        from activities.models import FanOut

        if not instance.local:
            return cls.updated

        cls.targets_fan_out(instance, FanOut.Types.identity_moved)
        return cls.moved_fanned_out

    @classmethod
    def handle_deleted(cls, instance: "Identity"):
        from activities.models import (
            FanOut,
            Post,
            PostInteraction,
            PostInteractionStates,
            PostStates,
            TimelineEvent,
        )
        from users.models import Bookmark, Follow, FollowStates, HashtagFollow, Report

        if not instance.local:
            return cls.updated

        # Delete local data
        TimelineEvent.objects.filter(identity=instance).delete()
        Bookmark.objects.filter(identity=instance).delete()
        HashtagFollow.objects.filter(identity=instance).delete()
        Report.objects.filter(source_identity=instance).delete()
        # Nullify all fields and fanout
        instance.name = ""
        instance.summary = ""
        instance.metadata = []
        instance.aliases = []
        instance.icon_uri = ""
        instance.discoverable = False
        instance.image.delete(save=False)
        instance.icon.delete(save=False)
        instance.save()
        cls.targets_fan_out(instance, FanOut.Types.identity_edited)
        # Delete all posts and interactions
        Post.transition_perform_queryset(instance.posts, PostStates.deleted)
        PostInteraction.transition_perform_queryset(
            instance.interactions, PostInteractionStates.undone
        )
        # Fanout the deletion and unfollow from both directions
        cls.targets_fan_out(instance, FanOut.Types.identity_deleted)
        for follower in Follow.objects.filter(target=instance):
            follower.transition_perform(FollowStates.rejecting)
        for following in Follow.objects.filter(source=instance):
            following.transition_perform(FollowStates.undone)

        return cls.deleted_fanned_out

    @classmethod
    def handle_outdated(cls, identity: "Identity"):
        # Local identities never need fetching
        if identity.local:
            return cls.updated
        # Run the actor fetch and progress to updated if it succeeds
        if identity.fetch_actor():
            return cls.updated

    @classmethod
    def handle_updated(cls, instance: "Identity"):
        if not instance.local and instance.state_age > Config.system.identity_max_age:
            return cls.outdated


class IdentityQuerySet(models.QuerySet):
    def not_deleted(self):
        query = self.exclude(state__in=IdentityStates.group_deleted())
        return query


class IdentityManager(models.Manager):
    def get_queryset(self):
        return IdentityQuerySet(self.model, using=self._db)

    def not_deleted(self):
        return self.get_queryset().not_deleted()


class Identity(StatorModel):
    """
    Represents both local and remote Fediverse identities (actors)
    """

    class Restriction(models.IntegerChoices):
        none = 0
        limited = 1
        blocked = 2

    ACTOR_TYPES = ["person", "service", "application", "group", "organization"]

    id = models.BigIntegerField(primary_key=True, default=Snowflake.generate_identity)

    # The Actor URI is essentially also a PK - we keep the default numeric
    # one around as well for making nice URLs etc.
    actor_uri = models.CharField(max_length=500, unique=True)

    state = StateField(IdentityStates)

    local = models.BooleanField(db_index=True)
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
    featured_collection_uri = models.CharField(max_length=500, blank=True, null=True)
    actor_type = models.CharField(max_length=100, default="person")

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

    # A list of other actor URIs - if this account was moved, should contain
    # the one URI it was moved to.
    aliases = models.JSONField(blank=True, null=True)

    # Admin-only moderation fields
    sensitive = models.BooleanField(default=False)
    restriction = models.IntegerField(
        choices=Restriction.choices, default=Restriction.none, db_index=True
    )
    admin_notes = models.TextField(null=True, blank=True)

    private_key = models.TextField(null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)
    public_key_id = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    fetched = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)

    objects = IdentityManager()

    ### Model attributes ###

    class Meta:
        verbose_name_plural = "identities"
        unique_together = [("username", "domain")]
        indexes: list = []  # We need this so Stator can add its own

    class urls(urlman.Urls):
        view = "/@{self.username}@{self.domain_id}/"
        replies = "{view}replies/"
        settings = "{view}settings/"
        action = "{view}action/"
        followers = "{view}followers/"
        following = "{view}following/"
        search = "{view}search/"
        activate = "{view}activate/"
        admin = "/admin/identities/"
        admin_edit = "{admin}{self.pk}/"
        djadmin_edit = "/djadmin/users/identity/{self.id}/change/"

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

    def all_absolute_profile_uris(self) -> list[str]:
        """
        Returns alist of profile URIs that are always absolute. For local addresses,
        this includes the short and long form URIs.
        """
        if not self.local:
            return [self.profile_uri]
        return [
            f"https://{self.domain.uri_domain}/@{self.username}/",
            f"https://{self.domain.uri_domain}/@{self.username}@{self.domain_id}/",
        ]

    def local_icon_url(self) -> RelativeAbsoluteUrl:
        """
        Returns an icon for use by us, with fallbacks to a placeholder
        """
        if self.icon:
            return RelativeAbsoluteUrl(self.icon.url)
        elif self.icon_uri:
            return ProxyAbsoluteUrl(
                f"/proxy/identity_icon/{self.pk}/",
                remote_url=self.icon_uri,
            )
        else:
            return StaticAbsoluteUrl("img/unknown-icon-128.png")

    def local_image_url(self) -> RelativeAbsoluteUrl | None:
        """
        Returns a background image for us, returning None if there isn't one
        """
        if self.image:
            return AutoAbsoluteUrl(self.image.url)
        elif self.image_uri:
            return ProxyAbsoluteUrl(
                f"/proxy/identity_image/{self.pk}/",
                remote_url=self.image_uri,
            )
        return None

    @property
    def safe_summary(self):
        return ContentRenderer(local=True).render_identity_summary(self.summary, self)

    @property
    def safe_metadata(self):
        renderer = ContentRenderer(local=True)

        if not self.metadata:
            return []
        return [
            {
                "name": renderer.render_identity_data(data["name"], self, strip=True),
                "value": renderer.render_identity_data(data["value"], self, strip=True),
            }
            for data in self.metadata
        ]

    def ensure_uris(self):
        """
        Ensures that local identities have all the URIs populated on their fields
        (this lets us add new ones easily)
        """
        if self.local:
            self.inbox_uri = self.actor_uri + "inbox/"
            self.outbox_uri = self.actor_uri + "outbox/"
            self.featured_collection_uri = self.actor_uri + "collections/featured/"
            self.followers_uri = self.actor_uri + "followers/"
            self.following_uri = self.actor_uri + "following/"
            self.shared_inbox_uri = f"https://{self.domain.uri_domain}/inbox/"

    def add_alias(self, actor_uri: str):
        self.aliases = (self.aliases or []) + [actor_uri]
        self.save()

    def remove_alias(self, actor_uri: str):
        self.aliases = [x for x in (self.aliases or []) if x != actor_uri]
        self.save()

    ### Alternate constructors/fetchers ###

    @classmethod
    def by_handle(cls, handle, fetch: bool = False) -> Optional["Identity"]:
        username, domain = handle.lstrip("@").split("@", 1)
        return cls.by_username_and_domain(username=username, domain=domain, fetch=fetch)

    @classmethod
    def by_username_and_domain(
        cls,
        username: str,
        domain: str | Domain,
        fetch: bool = False,
        local: bool = False,
    ) -> Optional["Identity"]:
        """
        Get an Identity by username and domain.

        When fetch is True, a failed lookup will do a webfinger lookup to attempt to do
        a lookup by actor_uri, creating an Identity record if one does not exist. When
        local is True, lookups will be restricted to local domains.

        If domain is a Domain, domain.local is used instead of passsed local.

        """
        if username.startswith("@"):
            raise ValueError("Username must not start with @")

        domain_instance = None

        if isinstance(domain, Domain):
            domain_instance = domain
            local = domain.local
            domain = domain.domain
        else:
            domain = domain.lower()
            domain_instance = Domain.get_domain(domain)
            local = domain_instance.local if domain_instance else local

        with transaction.atomic():
            try:
                if local:
                    return cls.objects.get(
                        username__iexact=username,
                        domain_id=domain,
                        local=True,
                    )
                else:
                    return cls.objects.get(
                        username__iexact=username,
                        domain_id=domain,
                    )
            except cls.DoesNotExist:
                if fetch and not local:
                    actor_uri, handle = cls.fetch_webfinger(f"{username}@{domain}")
                    if handle is None:
                        return None
                    # See if this actually does match an existing actor
                    try:
                        return cls.objects.get(actor_uri=actor_uri)
                    except cls.DoesNotExist:
                        pass
                    # OK, make one
                    username, domain = handle.split("@")
                    if not domain_instance:
                        domain_instance = Domain.get_remote_domain(domain)
                    return cls.objects.create(
                        actor_uri=actor_uri,
                        username=username,
                        domain_id=domain_instance,
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
                    # parallelism may cause another simultaneous worker thread
                    # to try to create the same identity - so use database level
                    # constructs to avoid an integrity error
                    identity, created = cls.objects.update_or_create(
                        actor_uri=uri, local=False
                    )
                    return identity
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
        return ContentRenderer(local=True).render_identity_data(
            self.name_or_handle, self, strip=True
        )

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

    def to_webfinger(self):
        aliases = [self.absolute_profile_uri()]

        actor_links = []

        if self.restriction != Identity.Restriction.blocked:
            # Blocked users don't get a profile page
            actor_links.append(
                {
                    "rel": "http://webfinger.net/rel/profile-page",
                    "type": "text/html",
                    "href": self.absolute_profile_uri(),
                },
            )

        # TODO: How to handle Restriction.limited and Restriction.blocked?
        #       Exposing the activity+json will allow migrating off server
        actor_links.extend(
            [
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": self.actor_uri,
                }
            ]
        )

        return {
            "subject": f"acct:{self.handle}",
            "aliases": aliases,
            "links": actor_links,
        }

    def to_ap(self):
        from activities.models import Emoji

        self.ensure_uris()
        response = {
            "id": self.actor_uri,
            "type": self.actor_type.title(),
            "inbox": self.inbox_uri,
            "outbox": self.outbox_uri,
            "featured": self.featured_collection_uri,
            "followers": self.followers_uri,
            "following": self.following_uri,
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
            response["summary"] = self.summary
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
        if self.shared_inbox_uri:
            response["endpoints"] = {
                "sharedInbox": self.shared_inbox_uri,
            }
        if self.metadata:
            response["attachment"] = [
                {
                    "type": "PropertyValue",
                    "name": FediverseHtmlParser(item["name"]).plain_text,
                    "value": FediverseHtmlParser(item["value"]).html,
                }
                for item in self.metadata
            ]
        if self.aliases:
            response["alsoKnownAs"] = self.aliases
        # Emoji
        emojis = Emoji.emojis_from_content(
            (self.name or "") + " " + (self.summary or ""), None
        )
        if emojis:
            response["tag"] = []
            for emoji in emojis:
                response["tag"].append(emoji.to_ap_tag())
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

    def to_update_ap(self):
        """
        Returns the AP JSON to update this object
        """
        object = self.to_ap()
        return {
            "type": "Update",
            "id": self.actor_uri + "#update",
            "actor": self.actor_uri,
            "object": object,
        }

    def to_delete_ap(self):
        """
        Returns the AP JSON to delete this object
        """
        object = self.to_ap()
        return {
            "type": "Delete",
            "id": self.actor_uri + "#delete",
            "actor": self.actor_uri,
            "object": object,
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

    ### Deletion ###

    def mark_deleted(self):
        """
        Marks the identity and all of its related content as deleted.
        """
        from api.models import Authorization, Token

        # Remove all login tokens
        Authorization.objects.filter(identity=self).delete()
        Token.objects.filter(identity=self).delete()
        # Remove all users from ourselves and mark deletion date
        self.users.set([])
        self.deleted = timezone.now()
        self.save()
        # Move ourselves to deleted
        self.transition_perform(IdentityStates.deleted)

    ### Actor/Webfinger fetching ###

    @classmethod
    def fetch_webfinger_url(cls, domain: str):
        """
        Given a domain (hostname), returns the correct webfinger URL to use
        based on probing host-meta.
        """
        with httpx.Client(
            timeout=settings.SETUP.REMOTE_TIMEOUT,
            headers={"User-Agent": settings.TAKAHE_USER_AGENT},
        ) as client:
            try:
                response = client.get(
                    f"https://{domain}/.well-known/host-meta",
                    follow_redirects=True,
                    headers={"Accept": "application/xml"},
                )

                # In the case of anything other than a success, we'll still try
                # hitting the webfinger URL on the domain we were given to handle
                # incorrectly setup servers.
                if response.status_code == 200 and response.content.strip():
                    tree = etree.fromstring(response.content)
                    template = tree.xpath(
                        "string(.//*[local-name() = 'Link' and @rel='lrdd' and (not(@type) or @type='application/jrd+json')]/@template)"
                    )
                    if template:
                        return template
            except (httpx.RequestError, etree.ParseError):
                pass

        return f"https://{domain}/.well-known/webfinger?resource={{uri}}"

    @classmethod
    def fetch_webfinger(cls, handle: str) -> tuple[str | None, str | None]:
        """
        Given a username@domain handle, returns a tuple of
        (actor uri, canonical handle) or None, None if it does not resolve.
        """
        domain = handle.split("@")[1].lower()
        try:
            webfinger_url = cls.fetch_webfinger_url(domain)
        except ssl.SSLCertVerificationError:
            return None, None

        # Go make a Webfinger request
        with httpx.Client(
            timeout=settings.SETUP.REMOTE_TIMEOUT,
            headers={"User-Agent": settings.TAKAHE_USER_AGENT},
        ) as client:
            try:
                response = client.get(
                    webfinger_url.format(uri=f"acct:{handle}"),
                    follow_redirects=True,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
            except (httpx.HTTPError, ssl.SSLCertVerificationError) as ex:
                response = getattr(ex, "response", None)
                if isinstance(ex, httpx.TimeoutException) or (
                    response and response.status_code in [408, 429, 504]
                ):
                    raise TryAgainLater() from ex
                elif (
                    response
                    and response.status_code < 500
                    and response.status_code not in [400, 401, 403, 404, 406, 410]
                ):
                    raise ValueError(
                        f"Client error fetching webfinger: {response.status_code}",
                        response.content,
                    )
                return None, None

        try:
            data = response.json()
        except ValueError:
            # Some servers return these with a 200 status code!
            if b"not found" in response.content.lower():
                return None, None
            raise ValueError(
                "JSON parse error fetching webfinger",
                response.content,
            )
        try:
            if data["subject"].startswith("acct:"):
                data["subject"] = data["subject"][5:]
            for link in data["links"]:
                if (
                    link.get("type") == "application/activity+json"
                    and link.get("rel") == "self"
                ):
                    return link["href"], data["subject"]
        except KeyError:
            # Server returning wrong payload structure
            pass
        return None, None

    @classmethod
    def fetch_pinned_post_uris(cls, uri: str) -> list[str]:
        """
        Fetch an identity's featured collection.
        """
        with httpx.Client(
            timeout=settings.SETUP.REMOTE_TIMEOUT,
            headers={"User-Agent": settings.TAKAHE_USER_AGENT},
        ) as client:
            try:
                response = client.get(
                    uri,
                    follow_redirects=True,
                    headers={"Accept": "application/activity+json"},
                )
                response.raise_for_status()
            except (httpx.HTTPError, ssl.SSLCertVerificationError) as ex:
                response = getattr(ex, "response", None)
                if isinstance(ex, httpx.TimeoutException) or (
                    response and response.status_code in [408, 429, 504]
                ):
                    raise TryAgainLater() from ex
                elif (
                    response
                    and response.status_code < 500
                    and response.status_code not in [401, 403, 404, 406, 410]
                ):
                    raise ValueError(
                        f"Client error fetching featured collection: {response.status_code}",
                        response.content,
                    )
                return []

        try:
            json_data = json_from_response(response)
            data = canonicalise(json_data, include_security=True)
            items: list[dict | str] = []
            if "orderedItems" in data:
                items = list(reversed(data["orderedItems"]))
            elif "items" in data:
                items = list(data["items"])

            ids = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                post_obj: dict | None = item
                if item["type"] in ["Create", "Update"]:
                    post_obj = item.get("object")
                if post_obj:
                    ids.append(post_obj["id"])
            return ids
        except ValueError:
            # Some servers return these with a 200 status code!
            if b"not found" in response.content.lower():
                return []
            raise ValueError(
                "JSON parse error fetching featured collection",
                response.content,
            )

    def fetch_actor(self) -> bool:
        """
        Fetches the user's actor information, as well as their domain from
        webfinger if it's available.
        """
        from activities.models import Emoji

        if self.local:
            raise ValueError("Cannot fetch local identities")
        try:
            response = SystemActor().signed_request(
                method="get",
                uri=self.actor_uri,
            )
        except httpx.TimeoutException:
            raise TryAgainLater()
        except (httpx.RequestError, ssl.SSLCertVerificationError):
            return False
        content_type = response.headers.get("content-type")
        if content_type and "html" in content_type:
            # Some servers don't properly handle "application/activity+json"
            return False
        status_code = response.status_code
        if status_code >= 400:
            if status_code in [408, 429, 504]:
                raise TryAgainLater()
            if status_code == 410 and self.pk:
                # Their account got deleted, so let's do the same.
                Identity.objects.filter(pk=self.pk).delete()
            if status_code < 500 and status_code not in [401, 403, 404, 406, 410]:
                logger.info(
                    "Client error fetching actor: %d %s", status_code, self.actor_uri
                )
            return False
        try:
            json_data = json_from_response(response)
            document = canonicalise(json_data, include_security=True)
        except ValueError:
            # servers with empty or invalid responses are inevitable
            logger.info(
                "Invalid response fetching actor %s",
                self.actor_uri,
                extra={
                    "content": response.content,
                },
            )
            return False
        if "type" not in document:
            return False
        self.name = document.get("name")
        self.profile_uri = document.get("url")
        self.inbox_uri = document.get("inbox")
        self.outbox_uri = document.get("outbox")
        self.followers_uri = document.get("followers")
        self.following_uri = document.get("following")
        self.featured_collection_uri = document.get("featured")
        self.actor_type = document["type"].lower()
        self.shared_inbox_uri = document.get("endpoints", {}).get("sharedInbox")
        self.summary = document.get("summary")
        self.username = document.get("preferredUsername")
        if self.username and "@value" in self.username:
            self.username = self.username["@value"]
        if self.username:
            self.username = self.username
        self.manually_approves_followers = document.get("manuallyApprovesFollowers")
        self.public_key = document.get("publicKey", {}).get("publicKeyPem")
        self.public_key_id = document.get("publicKey", {}).get("id")
        # Sometimes the public key PEM is in a language construct?
        if isinstance(self.public_key, dict):
            self.public_key = self.public_key["@value"]
        self.icon_uri = get_first_image_url(document.get("icon", None))
        self.image_uri = get_first_image_url(document.get("image", None))
        self.discoverable = document.get("toot:discoverable", True)
        # Profile links/metadata
        self.metadata = []
        for attachment in get_list(document, "attachment"):
            if (
                attachment["type"] == "PropertyValue"
                and "name" in attachment
                and "value" in attachment
            ):
                self.metadata.append(
                    {
                        "name": attachment["name"],
                        "value": FediverseHtmlParser(attachment["value"]).html,
                    }
                )
        # Now go do webfinger with that info to see if we can get a canonical domain
        actor_url_parts = urlparse(self.actor_uri)
        self.domain = Domain.get_remote_domain(actor_url_parts.hostname)
        if self.username:
            try:
                webfinger_actor, webfinger_handle = self.fetch_webfinger(
                    f"{self.username}@{actor_url_parts.hostname}"
                )
                if webfinger_handle:
                    webfinger_username, webfinger_domain = webfinger_handle.split("@")
                    self.username = webfinger_username
                    self.domain = Domain.get_remote_domain(webfinger_domain)
            except TryAgainLater:
                # continue with original domain when webfinger times out
                logger.info("WebFinger timed out: %s", self.actor_uri)
                pass
            except ValueError as exc:
                logger.info(
                    "Can't parse WebFinger: %s %s",
                    exc.args[0],
                    self.actor_uri,
                    exc_info=exc,
                )
                return False
        # Emojis (we need the domain so we do them here)
        for tag in get_list(document, "tag"):
            if tag["type"].lower() in ["toot:emoji", "emoji"]:
                Emoji.by_ap_tag(self.domain, tag, create=True)
        # Mark as fetched
        self.fetched = timezone.now()
        try:
            with transaction.atomic():
                # if we don't wrap this in its own transaction, the exception
                # handler is guaranteed to fail
                self.save()
        except IntegrityError as e:
            # See if we can fetch a PK and save there
            if self.pk is None:
                try:
                    other_row = Identity.objects.get(actor_uri=self.actor_uri)
                except Identity.DoesNotExist:
                    raise ValueError(
                        f"Could not save Identity at end of actor fetch: {e}"
                    )
                self.pk: int | None = other_row.pk
                with transaction.atomic():
                    self.save()

        # Fetch pinned posts in a followup task
        if self.featured_collection_uri:
            InboxMessage.create_internal(
                {
                    "type": "SyncPins",
                    "identity": self.pk,
                }
            )

        return True

    ### OpenGraph API ###

    def to_opengraph_dict(self) -> dict:
        return {
            "og:title": f"{self.name} (@{self.handle})",
            "og:type": "profile",
            "og:description": self.summary,
            "og:profile:username": self.handle,
            "og:image:url": self.local_icon_url().absolute,
            "og:image:height": 85,
            "og:image:width": 85,
        }

    ### Mastodon Client API ###

    def to_mastodon_mention_json(self):
        return {
            "id": self.id,
            "username": self.username or "",
            "url": self.absolute_profile_uri() or "",
            "acct": self.handle or "",
        }

    def to_mastodon_json(self, source=False, include_counts=True):
        from activities.models import Emoji, Post

        header_image = self.local_image_url()
        missing = StaticAbsoluteUrl("img/missing.png").absolute

        metadata_value_text = (
            " ".join([m["value"] for m in self.metadata]) if self.metadata else ""
        )
        emojis = Emoji.emojis_from_content(
            f"{self.name} {self.summary} {metadata_value_text}", self.domain
        )
        renderer = ContentRenderer(local=False)
        result = {
            "id": self.pk,
            "username": self.username or "",
            "acct": self.username if source else self.handle,
            "url": self.absolute_profile_uri() or "",
            "display_name": self.name or "",
            "note": self.summary or "",
            "avatar": self.local_icon_url().absolute,
            "avatar_static": self.local_icon_url().absolute,
            "header": header_image.absolute if header_image else missing,
            "header_static": header_image.absolute if header_image else missing,
            "locked": bool(self.manually_approves_followers),
            "fields": (
                [
                    {
                        "name": m["name"],
                        "value": renderer.render_identity_data(m["value"], self),
                        "verified_at": None,
                    }
                    for m in self.metadata
                ]
                if self.metadata
                else []
            ),
            "emojis": [emoji.to_mastodon_json() for emoji in emojis],
            "bot": self.actor_type.lower() in ["service", "application"],
            "group": self.actor_type.lower() == "group",
            "discoverable": self.discoverable,
            "suspended": False,
            "limited": False,
            "created_at": format_ld_date(
                self.created.replace(hour=0, minute=0, second=0, microsecond=0)
            ),
            "last_status_at": None,  # TODO: populate
            "statuses_count": self.posts.count() if include_counts else 0,
            "followers_count": self.inbound_follows.count() if include_counts else 0,
            "following_count": self.outbound_follows.count() if include_counts else 0,
        }
        if source:
            privacy_map = {
                Post.Visibilities.public: "public",
                Post.Visibilities.unlisted: "unlisted",
                Post.Visibilities.local_only: "unlisted",
                Post.Visibilities.followers: "private",
                Post.Visibilities.mentioned: "direct",
            }
            result["source"] = {
                "note": FediverseHtmlParser(self.summary).plain_text
                if self.summary
                else "",
                "fields": (
                    [
                        {
                            "name": m["name"],
                            "value": FediverseHtmlParser(m["value"]).plain_text,
                            "verified_at": None,
                        }
                        for m in self.metadata
                    ]
                    if self.metadata
                    else []
                ),
                "privacy": privacy_map[
                    Config.load_identity(self).default_post_visibility
                ],
                "sensitive": False,
                "language": "unk",
                "follow_requests_count": 0,
            }
        return result

    ### Cryptography ###

    def signed_request(
        self,
        method: Literal["get", "post"],
        uri: str,
        body: dict | None = None,
    ):
        """
        Performs a signed request on behalf of the System Actor.
        """
        return HttpSignature.signed_request(
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
