import re
from collections.abc import Iterable
from typing import Optional

import httpx
import urlman
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.postgres.indexes import GinIndex
from django.db import models, transaction
from django.template import loader
from django.template.defaultfilters import linebreaks_filter
from django.utils import timezone

from activities.models.emoji import Emoji
from activities.models.fan_out import FanOut
from activities.models.hashtag import Hashtag
from activities.models.post_types import (
    PostTypeData,
    PostTypeDataDecoder,
    PostTypeDataEncoder,
)
from core.html import ContentRenderer, strip_html
from core.ld import canonicalise, format_ld_date, get_list, parse_ld_date
from stator.exceptions import TryAgainLater
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.identity import Identity, IdentityStates
from users.models.system_actor import SystemActor


class PostStates(StateGraph):
    new = State(try_interval=300)
    fanned_out = State(externally_progressed=True)
    deleted = State(try_interval=300)
    deleted_fanned_out = State()

    edited = State(try_interval=300)
    edited_fanned_out = State(externally_progressed=True)

    new.transitions_to(fanned_out)
    fanned_out.transitions_to(deleted)
    fanned_out.transitions_to(edited)

    deleted.transitions_to(deleted_fanned_out)
    edited.transitions_to(edited_fanned_out)
    edited_fanned_out.transitions_to(edited)
    edited_fanned_out.transitions_to(deleted)

    @classmethod
    async def targets_fan_out(cls, post: "Post", type_: str) -> None:
        # Fan out to each target
        for follow in await post.aget_targets():
            await FanOut.objects.acreate(
                identity=follow,
                type=type_,
                subject_post=post,
            )

    @classmethod
    async def handle_new(cls, instance: "Post"):
        """
        Creates all needed fan-out objects for a new Post.
        """
        post = await instance.afetch_full()
        await cls.targets_fan_out(post, FanOut.Types.post)
        await post.ensure_hashtags()
        return cls.fanned_out

    @classmethod
    async def handle_deleted(cls, instance: "Post"):
        """
        Creates all needed fan-out objects needed to delete a Post.
        """
        post = await instance.afetch_full()
        await cls.targets_fan_out(post, FanOut.Types.post_deleted)
        return cls.deleted_fanned_out

    @classmethod
    async def handle_edited(cls, instance: "Post"):
        """
        Creates all needed fan-out objects for an edited Post.
        """
        post = await instance.afetch_full()
        await cls.targets_fan_out(post, FanOut.Types.post_edited)
        await post.ensure_hashtags()
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
            author__local=True,
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

    def visible_to(self, identity, include_replies: bool = False):
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
                visibility=Post.Visibilities.mentioned,
                mentions=identity,
            )
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
    in_reply_to = models.CharField(max_length=500, blank=True, null=True)

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
        ]

    class urls(urlman.Urls):
        view = "{self.author.urls.view}posts/{self.id}/"
        object_uri = "{self.author.actor_uri}posts/{self.id}/"
        action_like = "{view}like/"
        action_unlike = "{view}unlike/"
        action_boost = "{view}boost/"
        action_unboost = "{view}unboost/"
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

    ain_reply_to_post = sync_to_async(in_reply_to_post)

    ### Content cleanup and extraction ###
    def clean_type_data(self, value):
        PostTypeData.parse_obj(value)

    mention_regex = re.compile(
        r"(^|[^\w\d\-_/])@([\w\d\-_]+(?:@[\w\d\-_\.]+[\w\d\-_]+)?)"
    )

    def _safe_content_note(self, *, local: bool = True):
        return ContentRenderer(local=local).render_post(self.content, self)

    # def _safe_content_question(self, *, local: bool = True):
    #     context = {
    #         "post": self,
    #         "typed_data": PostTypeData(self.type_data),
    #     }
    #     return loader.render_to_string("activities/_type_question.html", context)

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

    ### Async helpers ###

    async def afetch_full(self) -> "Post":
        """
        Returns a version of the object with all relations pre-loaded
        """
        return (
            await Post.objects.select_related("author", "author__domain")
            .prefetch_related("mentions", "mentions__domain", "attachments", "emojis")
            .aget(pk=self.pk)
        )

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
    ) -> "Post":
        with transaction.atomic():
            # Find mentions in this post
            mentions = cls.mentions_from_content(content, author)
            if reply_to:
                mentions.add(reply_to.author)
                # Maintain local-only for replies
                if reply_to.visibility == reply_to.Visibilities.local_only:
                    visibility = reply_to.Visibilities.local_only
            # Find hashtags in this post
            hashtags = Hashtag.hashtags_from_content(content) or None
            # Find emoji in this post
            emojis = Emoji.emojis_from_content(content, None)
            # Strip all HTML and apply linebreaks filter
            content = linebreaks_filter(strip_html(content))
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
            post.save()
        return post

    def edit_local(
        self,
        content: str,
        summary: str | None = None,
        visibility: int = Visibilities.public,
        attachments: list | None = None,
    ):
        with transaction.atomic():
            # Strip all HTML and apply linebreaks filter
            self.content = linebreaks_filter(strip_html(content))
            self.summary = summary or None
            self.sensitive = bool(summary)
            self.visibility = visibility
            self.edited = timezone.now()
            self.hashtags = Hashtag.hashtags_from_content(content) or None
            self.mentions.set(self.mentions_from_content(content, self.author))
            self.emojis.set(Emoji.emojis_from_content(content, None))
            self.attachments.set(attachments or [])
            self.save()

    @classmethod
    def mentions_from_content(cls, content, author) -> set[Identity]:
        mention_hits = cls.mention_regex.findall(content)
        mentions = set()
        for precursor, handle in mention_hits:
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

    async def ensure_hashtags(self) -> None:
        """
        Ensure any of the already parsed hashtags from this Post
        have a corresponding Hashtag record.
        """
        # Ensure hashtags
        if self.hashtags:
            for hashtag in self.hashtags:
                await Hashtag.objects.aget_or_create(
                    hashtag=hashtag,
                )

    ### ActivityPub (outbound) ###

    def to_ap(self) -> dict:
        """
        Returns the AP JSON for this object
        """
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
        # TODO: Add followers object
        if self.visibility == self.Visibilities.public:
            value["to"].append("Public")
        elif self.visibility == self.Visibilities.unlisted:
            value["cc"].append("Public")
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

    async def aget_targets(self) -> Iterable[Identity]:
        """
        Returns a list of Identities that need to see posts and their changes
        """
        targets = set()
        async for mention in self.mentions.all():
            targets.add(mention)
        # Then, if it's not mentions only, also deliver to followers
        if self.visibility != Post.Visibilities.mentioned:
            async for follower in self.author.inbound_follows.select_related("source"):
                targets.add(follower.source)
        # If it's a reply, always include the original author if we know them
        reply_post = await self.ain_reply_to_post()
        if reply_post:
            targets.add(reply_post.author)
            # And if it's a reply to one of our own, we have to re-fan-out to
            # the original author's followers
            if reply_post.author.local:
                async for follower in reply_post.author.inbound_follows.select_related(
                    "source"
                ):
                    targets.add(follower.source)
        # If this is a remote post or local-only, filter to only include
        # local identities
        if not self.local or self.visibility == Post.Visibilities.local_only:
            targets = {target for target in targets if target.local}
        # If it's a local post, include the author
        if self.local:
            targets.add(self.author)
        return targets

    ### ActivityPub (inbound) ###

    @classmethod
    def by_ap(cls, data, create=False, update=False, fetch_author=False) -> "Post":
        """
        Retrieves a Post instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises DoesNotExist if it's not found and create is False,
        or it's from a blocked domain.
        """
        # Do we have one with the right ID?
        created = False
        try:
            post = cls.objects.select_related("author__domain").get(
                object_uri=data["id"]
            )
        except cls.DoesNotExist:
            if create:
                # Resolve the author
                author = Identity.by_actor_uri(data["attributedTo"], create=create)
                # If the author is not fetched yet, try again later
                if author.domain is None:
                    if fetch_author:
                        async_to_sync(author.fetch_actor)()
                        if author.domain is None:
                            raise TryAgainLater()
                    else:
                        raise TryAgainLater()
                # If the post is from a blocked domain, stop and drop
                if author.domain.blocked:
                    raise cls.DoesNotExist("Post is from a blocked domain")
                post = cls.objects.create(
                    object_uri=data["id"],
                    author=author,
                    content="",
                    local=False,
                    type=data["type"],
                )
                created = True
            else:
                raise cls.DoesNotExist(f"No post with ID {data['id']}", data)
        if update or created:
            post.type = data["type"]
            if post.type in (cls.Types.article, cls.Types.question):
                type_data = PostTypeData(__root__=data).__root__
                post.type_data = type_data.dict()
            # Get content in order of: content value, contentmap.und, any contentmap entry
            if "content" in data:
                post.content = data["content"]
            elif "contentMap" in data:
                if "und" in data["contentMap"]:
                    post.content = data["contentMap"]["und"]
                else:
                    post.content = list(data["contentMap"].values())[0]
            else:
                raise ValueError("Post has no content or content map")
            post.summary = data.get("summary")
            post.sensitive = data.get("sensitive", False)
            post.url = data.get("url")
            post.published = parse_ld_date(data.get("published"))
            post.edited = parse_ld_date(data.get("updated"))
            post.in_reply_to = data.get("inReplyTo")
            # Mentions and hashtags
            post.hashtags = []
            for tag in get_list(data, "tag"):
                if tag["type"].lower() == "mention":
                    mention_identity = Identity.by_actor_uri(tag["href"], create=True)
                    post.mentions.add(mention_identity)
                elif tag["type"].lower() in ["_:hashtag", "hashtag"]:
                    post.hashtags.append(tag["name"].lower().lstrip("#"))
                elif tag["type"].lower() in ["toot:emoji", "emoji"]:
                    emoji = Emoji.by_ap_tag(post.author.domain, tag, create=True)
                    post.emojis.add(emoji)
                else:
                    raise ValueError(f"Unknown tag type {tag['type']}")
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
            # Attachments
            # These have no IDs, so we have to wipe them each time
            post.attachments.all().delete()
            for attachment in get_list(data, "attachment"):
                if "focalPoint" in attachment:
                    focal_x, focal_y = attachment["focalPoint"]
                else:
                    focal_x, focal_y = None, None
                post.attachments.create(
                    remote_url=attachment["url"],
                    mimetype=attachment["mediaType"],
                    name=attachment.get("name"),
                    width=attachment.get("width"),
                    height=attachment.get("height"),
                    blurhash=attachment.get("blurhash"),
                    focal_x=focal_x,
                    focal_y=focal_y,
                )
            post.save()
        return post

    @classmethod
    def by_object_uri(cls, object_uri, fetch=False):
        """
        Gets the post by URI - either looking up locally, or fetching
        from the other end if it's not here.
        """
        try:
            return cls.objects.get(object_uri=object_uri)
        except cls.DoesNotExist:
            if fetch:
                try:
                    response = async_to_sync(SystemActor().signed_request)(
                        method="get", uri=object_uri
                    )
                except httpx.RequestError:
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
                post = cls.by_ap(
                    canonicalise(response.json(), include_security=True),
                    create=True,
                    update=True,
                    fetch_author=True,
                )
                # We may need to fetch the author too
                if post.author.state == IdentityStates.outdated:
                    async_to_sync(post.author.fetch_actor)()
                return post
            else:
                raise cls.DoesNotExist(f"Cannot find Post with URI {object_uri}")

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
            # Find our post by ID if we have one
            try:
                post = cls.by_object_uri(data["object"]["id"])
            except cls.DoesNotExist:
                # It's already been deleted
                return
            # Ensure the actor on the request authored the post
            if not post.author.actor_uri == data["actor"]:
                raise ValueError("Actor on delete does not match object")
            post.delete()

    ### Mastodon API ###

    def to_mastodon_json(self, interactions=None):
        reply_parent = None
        if self.in_reply_to:
            reply_parent = Post.objects.filter(object_uri=self.in_reply_to).first()
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
            "account": self.author.to_mastodon_json(),
            "content": self.safe_content_remote(),
            "visibility": visibility_mapping[self.visibility],
            "sensitive": self.sensitive,
            "spoiler_text": self.summary or "",
            "media_attachments": [
                attachment.to_mastodon_json() for attachment in self.attachments.all()
            ],
            "mentions": [
                {
                    "id": mention.id,
                    "username": mention.username or "",
                    "url": mention.absolute_profile_uri() or "",
                    "acct": mention.handle or "",
                }
                for mention in self.mentions.all()
                if mention.username
            ],
            "tags": (
                [{"name": tag, "url": "/tag/{tag}/"} for tag in self.hashtags]
                if self.hashtags
                else []
            ),
            "emojis": [emoji.to_mastodon_json() for emoji in self.emojis.usable()],
            "reblogs_count": self.interactions.filter(type="boost").count(),
            "favourites_count": self.interactions.filter(type="like").count(),
            "replies_count": 0,
            "url": self.absolute_object_uri(),
            "in_reply_to_id": reply_parent.pk if reply_parent else None,
            "in_reply_to_account_id": reply_parent.author.pk if reply_parent else None,
            "reblog": None,
            "poll": None,
            "card": None,
            "language": None,
            "text": self.safe_content_remote(),
            "edited_at": format_ld_date(self.edited) if self.edited else None,
        }
        if interactions:
            value["favourited"] = self.pk in interactions.get("like", [])
            value["reblogged"] = self.pk in interactions.get("boost", [])
        return value
