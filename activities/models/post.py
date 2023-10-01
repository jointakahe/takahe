import datetime
import json
import mimetypes
import ssl
from collections.abc import Iterable
from typing import Optional
from urllib.parse import urlparse

import httpx
import urlman
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models, transaction
from django.db.utils import IntegrityError
from django.template import loader
from django.template.defaultfilters import linebreaks_filter
from django.utils import timezone
from pyld.jsonld import JsonLdError

from activities.models.emoji import Emoji
from activities.models.fan_out import FanOut
from activities.models.hashtag import Hashtag, HashtagStates
from activities.models.post_types import (
    PostTypeData,
    PostTypeDataDecoder,
    PostTypeDataEncoder,
    QuestionData,
)
from core.exceptions import ActivityPubFormatError, capture_message
from core.html import ContentRenderer, FediverseHtmlParser
from core.ld import (
    canonicalise,
    format_ld_date,
    get_list,
    get_value_or_map,
    parse_ld_date,
)
from core.snowflake import Snowflake
from stator.exceptions import TryAgainLater
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.follow import FollowStates
from users.models.hashtag_follow import HashtagFollow
from users.models.identity import Identity, IdentityStates
from users.models.inbox_message import InboxMessage
from users.models.system_actor import SystemActor


class PostStates(StateGraph):
    new = State(try_interval=300)
    fanned_out = State(try_interval=86400 * 14)
    deleted = State(try_interval=300)
    deleted_fanned_out = State(delete_after=86400)

    edited = State(try_interval=300)
    edited_fanned_out = State(externally_progressed=True)

    new.transitions_to(fanned_out)
    fanned_out.transitions_to(deleted_fanned_out)
    fanned_out.transitions_to(deleted)
    fanned_out.transitions_to(edited)

    deleted.transitions_to(deleted_fanned_out)
    edited.transitions_to(edited_fanned_out)
    edited_fanned_out.transitions_to(edited)
    edited_fanned_out.transitions_to(deleted)

    @classmethod
    def targets_fan_out(cls, post: "Post", type_: str) -> None:
        # Fan out to each target
        for follow in post.get_targets():
            FanOut.objects.create(
                identity=follow,
                type=type_,
                subject_post=post,
            )

    @classmethod
    def handle_new(cls, instance: "Post"):
        """
        Creates all needed fan-out objects for a new Post.
        """
        # Only fan out if the post was published in the last day or it's local
        # (we don't want to fan out anything older that that which is remote)
        if instance.local or (timezone.now() - instance.published) < datetime.timedelta(
            days=1
        ):
            cls.targets_fan_out(instance, FanOut.Types.post)
        instance.ensure_hashtags()
        return cls.fanned_out

    @classmethod
    def handle_fanned_out(cls, instance: "Post"):
        """
        For remote posts, sees if we can delete them every so often.
        """
        # Skip all of this if the horizon is zero
        if settings.SETUP.REMOTE_PRUNE_HORIZON <= 0:
            return
        # To be a candidate for deletion, a post must be remote and old enough
        if instance.local:
            return
        if instance.created > timezone.now() - datetime.timedelta(
            days=settings.SETUP.REMOTE_PRUNE_HORIZON
        ):
            return
        # It must have no local interactions
        if instance.interactions.filter(identity__local=True).exists():
            return
        # OK, delete it!
        instance.delete()
        return cls.deleted_fanned_out

    @classmethod
    def handle_deleted(cls, instance: "Post"):
        """
        Creates all needed fan-out objects needed to delete a Post.
        """
        cls.targets_fan_out(instance, FanOut.Types.post_deleted)
        return cls.deleted_fanned_out

    @classmethod
    def handle_edited(cls, instance: "Post"):
        """
        Creates all needed fan-out objects for an edited Post.
        """
        cls.targets_fan_out(instance, FanOut.Types.post_edited)
        instance.ensure_hashtags()
        return cls.edited_fanned_out


class PostQuerySet(models.QuerySet):
    def not_hidden(self):
        query = self.exclude(
            state__in=[PostStates.deleted, PostStates.deleted_fanned_out]
        )
        return query

    def public(self, include_replies: bool = False):
        query = self.filter(
            visibility__in=[
                Post.Visibilities.public,
                Post.Visibilities.local_only,
            ],
        )
        if not include_replies:
            return query.filter(in_reply_to__isnull=True)
        return query

    def local_public(self, include_replies: bool = False):
        query = self.filter(
            visibility__in=[
                Post.Visibilities.public,
                Post.Visibilities.local_only,
            ],
            local=True,
        )
        if not include_replies:
            return query.filter(in_reply_to__isnull=True)
        return query

    def unlisted(self, include_replies: bool = False):
        query = self.filter(
            visibility__in=[
                Post.Visibilities.public,
                Post.Visibilities.local_only,
                Post.Visibilities.unlisted,
            ],
        )
        if not include_replies:
            return query.filter(in_reply_to__isnull=True)
        return query

    def visible_to(self, identity: Identity | None, include_replies: bool = False):
        if identity is None:
            return self.unlisted(include_replies=include_replies)
        query = self.filter(
            models.Q(
                visibility__in=[
                    Post.Visibilities.public,
                    Post.Visibilities.local_only,
                    Post.Visibilities.unlisted,
                ]
            )
            | models.Q(
                visibility=Post.Visibilities.followers,
                author__inbound_follows__source=identity,
            )
            | models.Q(
                mentions=identity,
            )
            | models.Q(author=identity)
        ).distinct()
        if not include_replies:
            return query.filter(in_reply_to__isnull=True)
        return query

    def tagged_with(self, hashtag: str | Hashtag):
        if isinstance(hashtag, str):
            tag_q = models.Q(hashtags__contains=hashtag)
        else:
            tag_q = models.Q(hashtags__contains=hashtag.hashtag)
            if hashtag.aliases:
                for alias in hashtag.aliases:
                    tag_q |= models.Q(hashtags__contains=alias)
        return self.filter(tag_q)


class PostManager(models.Manager):
    def get_queryset(self):
        return PostQuerySet(self.model, using=self._db)

    def not_hidden(self):
        return self.get_queryset().not_hidden()

    def public(self, include_replies: bool = False):
        return self.get_queryset().public(include_replies=include_replies)

    def local_public(self, include_replies: bool = False):
        return self.get_queryset().local_public(include_replies=include_replies)

    def unlisted(self, include_replies: bool = False):
        return self.get_queryset().unlisted(include_replies=include_replies)

    def tagged_with(self, hashtag: str | Hashtag):
        return self.get_queryset().tagged_with(hashtag=hashtag)


class Post(StatorModel):
    """
    A post (status, toot) that is either local or remote.
    """

    class Visibilities(models.IntegerChoices):
        public = 0
        local_only = 4
        unlisted = 1
        followers = 2
        mentioned = 3

    class Types(models.TextChoices):
        article = "Article"
        audio = "Audio"
        event = "Event"
        image = "Image"
        note = "Note"
        page = "Page"
        question = "Question"
        video = "Video"

    id = models.BigIntegerField(primary_key=True, default=Snowflake.generate_post)

    # The author (attributedTo) of the post
    author = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="posts",
    )

    # The state the post is in
    state = StateField(PostStates)

    # If it is our post or not
    local = models.BooleanField()

    # The canonical object ID
    object_uri = models.CharField(max_length=2048, blank=True, null=True, unique=True)

    # Who should be able to see this Post
    visibility = models.IntegerField(
        choices=Visibilities.choices,
        default=Visibilities.public,
    )

    # The main (HTML) content
    content = models.TextField()

    type = models.CharField(
        max_length=20,
        choices=Types.choices,
        default=Types.note,
    )
    type_data = models.JSONField(
        blank=True, null=True, encoder=PostTypeDataEncoder, decoder=PostTypeDataDecoder
    )

    # If the contents of the post are sensitive, and the summary (content
    # warning) to show if it is
    sensitive = models.BooleanField(default=False)
    summary = models.TextField(blank=True, null=True)

    # The public, web URL of this Post on the original server
    url = models.CharField(max_length=2048, blank=True, null=True)

    # The Post it is replying to as an AP ID URI
    # (as otherwise we'd have to pull entire threads to use IDs)
    in_reply_to = models.CharField(max_length=500, blank=True, null=True, db_index=True)

    # The identities the post is directly to (who can see it if not public)
    to = models.ManyToManyField(
        "users.Identity",
        related_name="posts_to",
        blank=True,
    )

    # The identities mentioned in the post
    mentions = models.ManyToManyField(
        "users.Identity",
        related_name="posts_mentioning",
        blank=True,
    )

    # Hashtags in the post
    hashtags = models.JSONField(blank=True, null=True)

    emojis = models.ManyToManyField(
        "activities.Emoji",
        related_name="posts_using_emoji",
        blank=True,
    )

    # Like/Boost/etc counts
    stats = models.JSONField(blank=True, null=True)

    # When the post was originally created (as opposed to when we received it)
    published = models.DateTimeField(default=timezone.now)

    # If the post has been edited after initial publication
    edited = models.DateTimeField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = PostManager()

    class Meta:
        indexes = [
            GinIndex(fields=["hashtags"], name="hashtags_gin"),
            GinIndex(
                SearchVector("content", config="english"),
                name="content_vector_gin",
            ),
            models.Index(
                fields=["visibility", "local", "published"],
                name="ix_post_local_public_published",
            ),
            models.Index(
                fields=["visibility", "local", "created"],
                name="ix_post_local_public_created",
            ),
        ]

    class urls(urlman.Urls):
        view = "{self.author.urls.view}posts/{self.id}/"
        object_uri = "{self.author.actor_uri}posts/{self.id}/"
        action_like = "{view}like/"
        action_unlike = "{view}unlike/"
        action_boost = "{view}boost/"
        action_unboost = "{view}unboost/"
        action_bookmark = "{view}bookmark/"
        action_unbookmark = "{view}unbookmark/"
        action_delete = "{view}delete/"
        action_edit = "{view}edit/"
        action_report = "{view}report/"
        action_reply = "/compose/?reply_to={self.id}"
        admin_edit = "/djadmin/activities/post/{self.id}/change/"

        def get_scheme(self, url):
            return "https"

        def get_hostname(self, url):
            return self.instance.author.domain.uri_domain

    def __str__(self):
        return f"{self.author} #{self.id}"

    def get_absolute_url(self):
        return self.urls.view

    def absolute_object_uri(self):
        """
        Returns an object URI that is always absolute, for sending out to
        other servers.
        """
        if self.local:
            return self.author.absolute_profile_uri() + f"posts/{self.id}/"
        else:
            return self.object_uri

    def in_reply_to_post(self) -> Optional["Post"]:
        """
        Returns the actual Post object we're replying to, if we can find it
        """
        if self.in_reply_to is None:
            return None
        return (
            Post.objects.filter(object_uri=self.in_reply_to)
            .select_related("author")
            .first()
        )

    ### Content cleanup and extraction ###
    def clean_type_data(self, value):
        PostTypeData.parse_obj(value)

    def _safe_content_note(self, *, local: bool = True):
        return ContentRenderer(local=local).render_post(self.content, self)

    def _safe_content_question(self, *, local: bool = True):
        if local:
            context = {
                "post": self,
                "sanitized_content": self._safe_content_note(local=local),
                "local_display": local,
            }
            return loader.render_to_string("activities/_type_question.html", context)
        else:
            return ContentRenderer(local=local).render_post(self.content, self)

    def _safe_content_typed(self, *, local: bool = True):
        context = {
            "post": self,
            "sanitized_content": self._safe_content_note(local=local),
            "local_display": local,
        }
        return loader.render_to_string(
            (
                f"activities/_type_{self.type.lower()}.html",
                "activities/_type_unknown.html",
            ),
            context,
        )

    def safe_content(self, *, local: bool = True):
        func = getattr(
            self, f"_safe_content_{self.type.lower()}", self._safe_content_typed
        )
        if callable(func):
            return func(local=local)
        return self._safe_content_note(local=local)  # fallback

    def safe_content_local(self):
        """
        Returns the content formatted for local display
        """
        return self.safe_content(local=True)

    def safe_content_remote(self):
        """
        Returns the content formatted for remote consumption
        """
        return self.safe_content(local=False)

    def summary_class(self) -> str:
        """
        Returns a CSS class name to identify this summary value
        """
        if not self.summary:
            return ""
        return "summary-{self.id}"

    @property
    def stats_with_defaults(self):
        """
        Returns the stats dict with counts of likes/etc. in it
        """
        return {
            "likes": self.stats.get("likes", 0) if self.stats else 0,
            "boosts": self.stats.get("boosts", 0) if self.stats else 0,
            "replies": self.stats.get("replies", 0) if self.stats else 0,
        }

    ### Local creation/editing ###

    @classmethod
    def create_local(
        cls,
        author: Identity,
        content: str,
        summary: str | None = None,
        sensitive: bool = False,
        visibility: int = Visibilities.public,
        reply_to: Optional["Post"] = None,
        attachments: list | None = None,
        question: dict | None = None,
    ) -> "Post":
        with transaction.atomic():
            # Find mentions in this post
            mentions = cls.mentions_from_content(content, author)
            if reply_to:
                mentions.add(reply_to.author)
                # Maintain local-only for replies
                if reply_to.visibility == reply_to.Visibilities.local_only:
                    visibility = reply_to.Visibilities.local_only
            # Find emoji in this post
            emojis = Emoji.emojis_from_content(content, None)
            # Strip all unwanted HTML and apply linebreaks filter, grabbing hashtags on the way
            parser = FediverseHtmlParser(linebreaks_filter(content), find_hashtags=True)
            content = parser.html
            hashtags = (
                sorted([tag[: Hashtag.MAXIMUM_LENGTH] for tag in parser.hashtags])
                or None
            )
            # Make the Post object
            post = cls.objects.create(
                author=author,
                content=content,
                summary=summary or None,
                sensitive=bool(summary) or sensitive,
                local=True,
                visibility=visibility,
                hashtags=hashtags,
                in_reply_to=reply_to.object_uri if reply_to else None,
            )
            post.object_uri = post.urls.object_uri
            post.url = post.absolute_object_uri()
            post.mentions.set(mentions)
            post.emojis.set(emojis)
            if attachments:
                post.attachments.set(attachments)
            if question:
                post.type = question["type"]
                post.type_data = PostTypeData(__root__=question).__root__
            post.save()
            # Recalculate parent stats for replies
            if reply_to:
                reply_to.calculate_stats()
        return post

    def edit_local(
        self,
        content: str,
        summary: str | None = None,
        sensitive: bool | None = None,
        visibility: int = Visibilities.public,
        attachments: list | None = None,
        attachment_attributes: list | None = None,
    ):
        with transaction.atomic():
            # Strip all HTML and apply linebreaks filter
            parser = FediverseHtmlParser(linebreaks_filter(content), find_hashtags=True)
            self.content = parser.html
            self.hashtags = (
                sorted([tag[: Hashtag.MAXIMUM_LENGTH] for tag in parser.hashtags])
                or None
            )
            self.summary = summary or None
            self.sensitive = bool(summary) if sensitive is None else sensitive
            self.visibility = visibility
            self.edited = timezone.now()
            self.mentions.set(self.mentions_from_content(content, self.author))
            self.emojis.set(Emoji.emojis_from_content(content, None))
            self.attachments.set(attachments or [])
            self.save()

            for attrs in attachment_attributes or []:
                attachment = next(
                    (a for a in attachments or [] if str(a.id) == attrs.id), None
                )
                if attachment is None:
                    continue
                attachment.name = attrs.description
                attachment.save()

            self.transition_perform(PostStates.edited)

    @classmethod
    def mentions_from_content(cls, content, author) -> set[Identity]:
        mention_hits = FediverseHtmlParser(content, find_mentions=True).mentions
        mentions = set()
        for handle in mention_hits:
            handle = handle.lower()
            if "@" in handle:
                username, domain = handle.split("@", 1)
            else:
                username = handle
                domain = author.domain_id
            identity = Identity.by_username_and_domain(
                username=username,
                domain=domain,
                fetch=True,
            )
            if identity is not None:
                mentions.add(identity)
        return mentions

    def ensure_hashtags(self) -> None:
        """
        Ensure any of the already parsed hashtags from this Post
        have a corresponding Hashtag record.
        """
        # Ensure hashtags
        if self.hashtags:
            for hashtag in self.hashtags:
                tag, _ = Hashtag.objects.get_or_create(
                    hashtag=hashtag[: Hashtag.MAXIMUM_LENGTH],
                )
                tag.transition_perform(HashtagStates.outdated)

    def calculate_stats(self, save=True):
        """
        Recalculates our stats dict
        """
        from activities.models import PostInteraction, PostInteractionStates

        self.stats = {
            "likes": self.interactions.filter(
                type=PostInteraction.Types.like,
                state__in=PostInteractionStates.group_active(),
            ).count(),
            "boosts": self.interactions.filter(
                type=PostInteraction.Types.boost,
                state__in=PostInteractionStates.group_active(),
            ).count(),
            "replies": Post.objects.filter(in_reply_to=self.object_uri).count(),
        }
        if save:
            self.save()

    def calculate_type_data(self, save=True):
        """
        Recalculate type_data (used mostly for poll votes)
        """
        from activities.models import PostInteraction

        if self.local and isinstance(self.type_data, QuestionData):
            self.type_data.voter_count = (
                self.interactions.filter(
                    type=PostInteraction.Types.vote,
                )
                .values("identity")
                .distinct()
                .count()
            )

            for option in self.type_data.options:
                option.votes = self.interactions.filter(
                    type=PostInteraction.Types.vote,
                    value=option.name,
                ).count()
        if save:
            self.save()

    ### ActivityPub (outbound) ###

    def to_ap(self) -> dict:
        """
        Returns the AP JSON for this object
        """
        self.author.ensure_uris()
        value = {
            "to": [],
            "cc": [],
            "type": self.type,
            "id": self.object_uri,
            "published": format_ld_date(self.published),
            "attributedTo": self.author.actor_uri,
            "content": self.safe_content_remote(),
            "sensitive": self.sensitive,
            "url": self.absolute_object_uri(),
            "tag": [],
            "attachment": [],
        }
        if self.type == Post.Types.question and self.type_data:
            value[self.type_data.mode] = [
                {
                    "name": option.name,
                    "type": option.type,
                    "replies": {"type": "Collection", "totalItems": option.votes},
                }
                for option in self.type_data.options
            ]
            value["toot:votersCount"] = self.type_data.voter_count
            if self.type_data.end_time:
                value["endTime"] = format_ld_date(self.type_data.end_time)
        if self.summary:
            value["summary"] = self.summary
        if self.in_reply_to:
            value["inReplyTo"] = self.in_reply_to
        if self.edited:
            value["updated"] = format_ld_date(self.edited)
        # Targeting
        if self.visibility == self.Visibilities.public:
            value["to"].append("as:Public")
        elif self.visibility == self.Visibilities.unlisted:
            value["cc"].append("as:Public")
        elif (
            self.visibility == self.Visibilities.followers and self.author.followers_uri
        ):
            value["to"].append(self.author.followers_uri)
        # Mentions
        for mention in self.mentions.all():
            value["tag"].append(mention.to_ap_tag())
            value["cc"].append(mention.actor_uri)
        # Hashtags
        for hashtag in self.hashtags or []:
            value["tag"].append(
                {
                    "href": f"https://{self.author.domain.uri_domain}/tags/{hashtag}/",
                    "name": f"#{hashtag}",
                    "type": "Hashtag",
                }
            )
        # Emoji
        for emoji in self.emojis.all():
            value["tag"].append(emoji.to_ap_tag())
        # Attachments
        for attachment in self.attachments.all():
            value["attachment"].append(attachment.to_ap())
        # Remove fields if they're empty
        for field in ["to", "cc", "tag", "attachment"]:
            if not value[field]:
                del value[field]
        return value

    def to_create_ap(self):
        """
        Returns the AP JSON to create this object
        """
        object = self.to_ap()
        return {
            "to": object.get("to", []),
            "cc": object.get("cc", []),
            "type": "Create",
            "id": self.object_uri + "#create",
            "actor": self.author.actor_uri,
            "object": object,
        }

    def to_update_ap(self):
        """
        Returns the AP JSON to update this object
        """
        object = self.to_ap()
        return {
            "to": object.get("to", []),
            "cc": object.get("cc", []),
            "type": "Update",
            "id": self.object_uri + "#update",
            "actor": self.author.actor_uri,
            "object": object,
        }

    def to_delete_ap(self):
        """
        Returns the AP JSON to create this object
        """
        object = self.to_ap()
        return {
            "to": object.get("to", []),
            "cc": object.get("cc", []),
            "type": "Delete",
            "id": self.object_uri + "#delete",
            "actor": self.author.actor_uri,
            "object": object,
        }

    def get_targets(self) -> Iterable[Identity]:
        """
        Returns a list of Identities that need to see posts and their changes
        """
        targets = set()
        for mention in self.mentions.all():
            targets.add(mention)
        # Then, if it's not mentions only, also deliver to followers and all hashtag followers
        if self.visibility != Post.Visibilities.mentioned:
            for follower in self.author.inbound_follows.filter(
                state__in=FollowStates.group_active()
            ).select_related("source"):
                targets.add(follower.source)
            if self.hashtags:
                for follow in HashtagFollow.objects.by_hashtags(
                    self.hashtags
                ).prefetch_related("identity"):
                    targets.add(follow.identity)

        # If it's a reply, always include the original author if we know them
        reply_post = self.in_reply_to_post()
        if reply_post:
            targets.add(reply_post.author)
            # And if it's a reply to one of our own, we have to re-fan-out to
            # the original author's followers
            if reply_post.author.local:
                for follower in reply_post.author.inbound_follows.filter(
                    state__in=FollowStates.group_active()
                ).select_related("source"):
                    targets.add(follower.source)
        # If this is a remote post or local-only, filter to only include
        # local identities
        if not self.local or self.visibility == Post.Visibilities.local_only:
            targets = {target for target in targets if target.local}
        # If it's a local post, include the author
        if self.local:
            targets.add(self.author)
        # Fetch the author's full blocks and remove them as targets
        blocks = (
            self.author.outbound_blocks.active()
            .filter(mute=False)
            .select_related("target")
        )
        for block in blocks:
            try:
                targets.remove(block.target)
            except KeyError:
                pass
        # Now dedupe the targets based on shared inboxes (we only keep one per
        # shared inbox)
        deduped_targets = set()
        shared_inboxes = set()
        for target in targets:
            if target.local or not target.shared_inbox_uri:
                deduped_targets.add(target)
            elif target.shared_inbox_uri not in shared_inboxes:
                shared_inboxes.add(target.shared_inbox_uri)
                deduped_targets.add(target)
            else:
                # Their shared inbox is already being sent to
                pass
        return deduped_targets

    ### ActivityPub (inbound) ###

    @classmethod
    def by_ap(cls, data, create=False, update=False, fetch_author=False) -> "Post":
        """
        Retrieves a Post instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises DoesNotExist if it's not found and create is False,
        or it's from a blocked domain.
        """
        try:
            # Ensure data has the primary fields of all Posts
            if (
                not isinstance(data["id"], str)
                or not isinstance(data["attributedTo"], str)
                or not isinstance(data["type"], str)
            ):
                raise TypeError()
            # Ensure the domain of the object's actor and ID match to prevent injection
            if urlparse(data["id"]).hostname != urlparse(data["attributedTo"]).hostname:
                raise ValueError("Object's ID domain is different to its author")
        except (TypeError, KeyError) as ex:
            raise cls.DoesNotExist(
                "Object data is not a recognizable ActivityPub object"
            ) from ex

        # Do we have one with the right ID?
        created = False
        try:
            post: Post = cls.objects.select_related("author__domain").get(
                object_uri=data["id"]
            )
        except cls.DoesNotExist:
            if create:
                # Resolve the author
                author = Identity.by_actor_uri(data["attributedTo"], create=create)
                # If the author is not fetched yet, try again later
                if author.domain is None:
                    if fetch_author:
                        if not author.fetch_actor() or author.domain is None:
                            raise TryAgainLater()
                    else:
                        raise TryAgainLater()
                # If the post is from a blocked domain, stop and drop
                if author.domain.recursively_blocked():
                    raise cls.DoesNotExist("Post is from a blocked domain")
                # parallelism may cause another simultaneous worker thread
                # to try to create the same post - so watch for that and
                # try to avoid failing the entire transaction
                try:
                    # wrapped in a transaction to avoid breaking the outer
                    # transaction
                    with transaction.atomic():
                        post = cls.objects.create(
                            object_uri=data["id"],
                            author=author,
                            content="",
                            local=False,
                            type=data["type"],
                        )
                        created = True
                except IntegrityError:
                    # despite previous checks, a parallel thread managed
                    # to create the same object already
                    post = cls.by_object_uri(object_uri=data["id"])
            else:
                raise cls.DoesNotExist(f"No post with ID {data['id']}", data)
        if update or created:
            post.type = data["type"]
            post.url = data.get("url", data["id"])
            if post.type in (cls.Types.article, cls.Types.question):
                post.type_data = PostTypeData(__root__=data).__root__
            try:
                # apparently sometimes posts (Pages?) in the fediverse
                # don't have content, but this shouldn't be a total failure
                post.content = get_value_or_map(data, "content", "contentMap")
            except ActivityPubFormatError as err:
                capture_message(f"{err} on {post.url}")
                post.content = None
            # Document types have names, not summaries
            post.summary = data.get("summary") or data.get("name")
            if not post.content and post.summary:
                post.content = post.summary
                post.summary = None
            post.sensitive = data.get("sensitive", False)
            post.published = parse_ld_date(data.get("published"))
            post.edited = parse_ld_date(data.get("updated"))
            post.in_reply_to = data.get("inReplyTo")
            # Mentions and hashtags
            post.hashtags = []
            for tag in get_list(data, "tag"):
                tag_type = tag["type"].lower()
                if tag_type == "mention":
                    mention_identity = Identity.by_actor_uri(tag["href"], create=True)
                    post.mentions.add(mention_identity)
                elif tag_type in ["_:hashtag", "hashtag"]:
                    # kbin produces tags with 'tag' instead of 'name'
                    if "tag" in tag and "name" not in tag:
                        name = get_value_or_map(tag, "tag", "tagMap")
                    else:
                        name = get_value_or_map(tag, "name", "nameMap")
                    post.hashtags.append(
                        name.lower().lstrip("#")[: Hashtag.MAXIMUM_LENGTH]
                    )
                elif tag_type in ["toot:emoji", "emoji"]:
                    emoji = Emoji.by_ap_tag(post.author.domain, tag, create=True)
                    post.emojis.add(emoji)
                else:
                    # Various ActivityPub implementations and proposals introduced tag
                    # types, e.g. Edition in Bookwyrm and Link in fep-e232 Object Links
                    # it should be safe to ignore (and log) them before a full support
                    pass
            # Visibility and to
            # (a post is public if it's to:public, otherwise it's unlisted if
            # it's cc:public, otherwise it's more limited)
            to = [x.lower() for x in get_list(data, "to")]
            cc = [x.lower() for x in get_list(data, "cc")]
            post.visibility = Post.Visibilities.mentioned
            if "public" in to or "as:public" in to:
                post.visibility = Post.Visibilities.public
            elif "public" in cc or "as:public" in cc:
                post.visibility = Post.Visibilities.unlisted
            elif post.author.followers_uri in to:
                post.visibility = Post.Visibilities.followers
            # Attachments
            # These have no IDs, so we have to wipe them each time
            post.attachments.all().delete()
            for attachment in get_list(data, "attachment"):
                if "url" not in attachment and "href" in attachment:
                    # Links have hrefs, while other Objects have urls
                    attachment["url"] = attachment["href"]
                if "focalPoint" in attachment:
                    try:
                        focal_x, focal_y = attachment["focalPoint"]
                    except (ValueError, TypeError):
                        focal_x, focal_y = None, None
                else:
                    focal_x, focal_y = None, None
                mimetype = attachment.get("mediaType")
                if not mimetype or not isinstance(mimetype, str):
                    if "url" not in attachment:
                        raise ActivityPubFormatError(
                            f"No URL present on attachment in {post.url}"
                        )
                    mimetype, _ = mimetypes.guess_type(attachment["url"])
                    if not mimetype:
                        mimetype = "application/octet-stream"
                post.attachments.create(
                    remote_url=attachment["url"],
                    mimetype=mimetype,
                    name=attachment.get("name"),
                    width=attachment.get("width"),
                    height=attachment.get("height"),
                    blurhash=attachment.get("blurhash"),
                    focal_x=focal_x,
                    focal_y=focal_y,
                )
            # Calculate stats in case we have existing replies
            post.calculate_stats(save=False)
            with transaction.atomic():
                # if we don't commit the transaction here, there's a chance
                # the parent fetch below goes into an infinite loop
                post.save()

            # Potentially schedule a fetch of the reply parent, and recalculate
            # its stats if it's here already.
            if post.in_reply_to:
                try:
                    parent = cls.by_object_uri(post.in_reply_to)
                except cls.DoesNotExist:
                    try:
                        cls.ensure_object_uri(post.in_reply_to, reason=post.object_uri)
                    except ValueError:
                        capture_message(
                            f"Cannot fetch ancestor of Post={post.pk}, ancestor_uri={post.in_reply_to}"
                        )
                else:
                    parent.calculate_stats()
        return post

    @classmethod
    def by_object_uri(cls, object_uri, fetch=False) -> "Post":
        """
        Gets the post by URI - either looking up locally, or fetching
        from the other end if it's not here.
        """
        try:
            return cls.objects.get(object_uri=object_uri)
        except cls.DoesNotExist:
            if fetch:
                try:
                    response = SystemActor().signed_request(
                        method="get", uri=object_uri
                    )
                except (httpx.HTTPError, ssl.SSLCertVerificationError):
                    raise cls.DoesNotExist(f"Could not fetch {object_uri}")
                if response.status_code in [404, 410]:
                    raise cls.DoesNotExist(f"No post at {object_uri}")
                if response.status_code >= 500:
                    raise cls.DoesNotExist(f"Server error fetching {object_uri}")
                if response.status_code >= 400:
                    raise cls.DoesNotExist(
                        f"Error fetching post from {object_uri}: {response.status_code}",
                        {response.content},
                    )
                try:
                    post = cls.by_ap(
                        canonicalise(response.json(), include_security=True),
                        create=True,
                        update=True,
                        fetch_author=True,
                    )
                except (json.JSONDecodeError, ValueError, JsonLdError) as err:
                    raise cls.DoesNotExist(
                        f"Invalid ld+json response for {object_uri}"
                    ) from err
                # We may need to fetch the author too
                if post.author.state == IdentityStates.outdated:
                    post.author.fetch_actor()
                return post
            else:
                raise cls.DoesNotExist(f"Cannot find Post with URI {object_uri}")

    @classmethod
    def ensure_object_uri(cls, object_uri: str, reason: str | None = None):
        """
        Sees if the post is in our local set, and if not, schedules a fetch
        for it (in the background)
        """
        if not object_uri or "://" not in object_uri:
            raise ValueError("URI missing or invalid")
        try:
            cls.by_object_uri(object_uri)
        except cls.DoesNotExist:
            InboxMessage.create_internal(
                {
                    "type": "FetchPost",
                    "object": object_uri,
                    "reason": reason,
                }
            )

    @classmethod
    def handle_create_ap(cls, data):
        """
        Handles an incoming create request
        """
        with transaction.atomic():
            # Ensure the Create actor is the Post's attributedTo
            if data["actor"] != data["object"]["attributedTo"]:
                raise ValueError("Create actor does not match its Post object", data)
            # Create it, stator will fan it out locally
            cls.by_ap(data["object"], create=True, update=True)

    @classmethod
    def handle_update_ap(cls, data):
        """
        Handles an incoming update request
        """
        with transaction.atomic():
            # Ensure the Create actor is the Post's attributedTo
            if data["actor"] != data["object"]["attributedTo"]:
                raise ValueError("Create actor does not match its Post object", data)
            # Find it and update it
            try:
                cls.by_ap(data["object"], create=False, update=True)
            except cls.DoesNotExist:
                # We don't have a copy - assume we got a delete first and ignore.
                pass

    @classmethod
    def handle_delete_ap(cls, data):
        """
        Handles an incoming delete request
        """
        with transaction.atomic():
            # Is this an embedded object or plain ID?
            if isinstance(data["object"], str):
                object_uri = data["object"]
            else:
                object_uri = data["object"]["id"]
            # Find our post by ID if we have one
            try:
                post = cls.by_object_uri(object_uri)
            except cls.DoesNotExist:
                # It's already been deleted
                return
            # Ensure the actor on the request authored the post
            if not post.author.actor_uri == data["actor"]:
                raise ValueError("Actor on delete does not match object")
            post.delete()

    @classmethod
    def handle_fetch_internal(cls, data):
        """
        Handles an internal fetch-request inbox message
        """
        try:
            uri = data["object"]
            if "://" in uri:
                cls.by_object_uri(uri, fetch=True)
        except (cls.DoesNotExist, KeyError):
            pass

    ### OpenGraph API ###

    def to_opengraph_dict(self) -> dict:
        return {
            "og:title": f"{self.author.name} (@{self.author.handle})",
            "og:type": "article",
            "og:published_time": (self.published or self.created).isoformat(),
            "og:modified_time": (
                self.edited or self.published or self.created
            ).isoformat(),
            "og:description": (self.summary or self.safe_content_local()),
            "og:image:url": self.author.local_icon_url().absolute,
            "og:image:height": 85,
            "og:image:width": 85,
        }

    ### Mastodon API ###

    def to_mastodon_json(self, interactions=None, bookmarks=None, identity=None):
        reply_parent = None
        if self.in_reply_to:
            # Load the PK and author.id explicitly to prevent a SELECT on the entire author Identity
            reply_parent = (
                Post.objects.filter(object_uri=self.in_reply_to)
                .only("pk", "author_id")
                .first()
            )
        visibility_mapping = {
            self.Visibilities.public: "public",
            self.Visibilities.unlisted: "unlisted",
            self.Visibilities.followers: "private",
            self.Visibilities.mentioned: "direct",
            self.Visibilities.local_only: "public",
        }
        value = {
            "id": self.pk,
            "uri": self.object_uri,
            "created_at": format_ld_date(self.published),
            "account": self.author.to_mastodon_json(include_counts=False),
            "content": self.safe_content_remote(),
            "visibility": visibility_mapping[self.visibility],
            "sensitive": self.sensitive,
            "spoiler_text": self.summary or "",
            "media_attachments": [
                attachment.to_mastodon_json() for attachment in self.attachments.all()
            ],
            "mentions": [
                mention.to_mastodon_mention_json() for mention in self.mentions.all()
            ],
            "tags": (
                [
                    {
                        "name": tag,
                        "url": f"https://{self.author.domain.uri_domain}/tags/{tag}/",
                    }
                    for tag in self.hashtags
                ]
                if self.hashtags
                else []
            ),
            # Filter in the list comp rather than query because the common case is no emoji in the resultset
            # When filter is on emojis like `emojis.usable()` it causes a query that is not cached by prefetch_related
            "emojis": [
                emoji.to_mastodon_json()
                for emoji in self.emojis.all()
                if emoji.is_usable
            ],
            "reblogs_count": self.stats_with_defaults["boosts"],
            "favourites_count": self.stats_with_defaults["likes"],
            "replies_count": self.stats_with_defaults["replies"],
            "url": self.absolute_object_uri(),
            "in_reply_to_id": reply_parent.pk if reply_parent else None,
            "in_reply_to_account_id": (
                reply_parent.author_id if reply_parent else None
            ),
            "reblog": None,
            "poll": self.type_data.to_mastodon_json(self, identity)
            if isinstance(self.type_data, QuestionData)
            else None,
            "card": None,
            "language": None,
            "text": self.safe_content_remote(),
            "edited_at": format_ld_date(self.edited) if self.edited else None,
        }
        if interactions:
            value["favourited"] = self.pk in interactions.get("like", [])
            value["reblogged"] = self.pk in interactions.get("boost", [])
            value["pinned"] = self.pk in interactions.get("pin", [])
        if bookmarks:
            value["bookmarked"] = self.pk in bookmarks
        return value
