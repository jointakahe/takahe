import re
from collections.abc import Iterable
from typing import Optional

import httpx
import urlman
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.postgres.indexes import GinIndex
from django.db import models, transaction
from django.template.defaultfilters import linebreaks_filter
from django.utils import timezone
from django.utils.safestring import mark_safe

from activities.models.fan_out import FanOut
from activities.models.hashtag import Hashtag
from core.html import sanitize_post, strip_html
from core.ld import canonicalise, format_ld_date, get_list, parse_ld_date
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

    def public(self, include_replies: bool = False):
        return self.get_queryset().public(include_replies=include_replies)

    def local_public(self, include_replies: bool = False):
        return self.get_queryset().local_public(include_replies=include_replies)

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
    object_uri = models.CharField(max_length=500, blank=True, null=True, unique=True)

    # Who should be able to see this Post
    visibility = models.IntegerField(
        choices=Visibilities.choices,
        default=Visibilities.public,
    )

    # The main (HTML) content
    content = models.TextField()

    # If the contents of the post are sensitive, and the summary (content
    # warning) to show if it is
    sensitive = models.BooleanField(default=False)
    summary = models.TextField(blank=True, null=True)

    # The public, web URL of this Post on the original server
    url = models.CharField(max_length=500, blank=True, null=True)

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
        action_reply = "/compose/?reply_to={self.id}"

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
        return (
            Post.objects.filter(object_uri=self.in_reply_to)
            .select_related("author")
            .first()
        )

    ain_reply_to_post = sync_to_async(in_reply_to_post)

    ### Content cleanup and extraction ###

    mention_regex = re.compile(
        r"(^|[^\w\d\-_])@([\w\d\-_]+(?:@[\w\d\-_]+\.[\w\d\-_\.]+)?)"
    )

    def linkify_mentions(self, content, local=False):
        """
        Links mentions _in the context of the post_ - as in, using the mentions
        property as the only source (as we might be doing this without other
        DB access allowed)
        """

        possible_matches = {}
        for mention in self.mentions.all():
            if local:
                url = str(mention.urls.view)
            else:
                url = mention.absolute_profile_uri()
            possible_matches[mention.username] = url
            possible_matches[f"{mention.username}@{mention.domain_id}"] = url

        collapse_name: dict[str, str] = {}

        def replacer(match):
            precursor = match.group(1)
            handle = match.group(2).lower()
            if "@" in handle:
                short_handle = handle.split("@", 1)[0]
            else:
                short_handle = handle
            if handle in possible_matches:
                if short_handle not in collapse_name:
                    collapse_name[short_handle] = handle
                elif collapse_name.get(short_handle) != handle:
                    short_handle = handle
                return f'{precursor}<a href="{possible_matches[handle]}">@{short_handle}</a>'
            else:
                return match.group()

        return mark_safe(self.mention_regex.sub(replacer, content))

    def safe_content_local(self):
        """
        Returns the content formatted for local display
        """
        return Hashtag.linkify_hashtags(
            self.linkify_mentions(sanitize_post(self.content), local=True)
        )

    def safe_content_remote(self):
        """
        Returns the content formatted for remote consumption
        """
        return self.linkify_mentions(sanitize_post(self.content))

    def safe_content_plain(self):
        """
        Returns the content formatted as plain text
        """
        return self.linkify_mentions(sanitize_post(self.content))

    ### Async helpers ###

    async def afetch_full(self) -> "Post":
        """
        Returns a version of the object with all relations pre-loaded
        """
        return (
            await Post.objects.select_related("author", "author__domain")
            .prefetch_related("mentions", "mentions__domain", "attachments")
            .aget(pk=self.pk)
        )

    ### Local creation/editing ###

    @classmethod
    def create_local(
        cls,
        author: Identity,
        content: str,
        summary: str | None = None,
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
            # Strip all HTML and apply linebreaks filter
            content = linebreaks_filter(strip_html(content))
            # Make the Post object
            post = cls.objects.create(
                author=author,
                content=content,
                summary=summary or None,
                sensitive=bool(summary),
                local=True,
                visibility=visibility,
                hashtags=hashtags,
                in_reply_to=reply_to.object_uri if reply_to else None,
            )
            post.object_uri = post.urls.object_uri
            post.url = post.absolute_object_uri()
            post.mentions.set(mentions)
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
            "to": "as:Public",
            "cc": [],
            "type": "Note",
            "id": self.object_uri,
            "published": format_ld_date(self.published),
            "attributedTo": self.author.actor_uri,
            "content": self.safe_content_remote(),
            "as:sensitive": self.sensitive,
            "url": self.absolute_object_uri(),
            "tag": [],
            "attachment": [],
        }
        if self.summary:
            value["summary"] = self.summary
        if self.in_reply_to:
            value["inReplyTo"] = self.in_reply_to
        if self.edited:
            value["updated"] = format_ld_date(self.edited)
        # Mentions
        for mention in self.mentions.all():
            value["tag"].append(
                {
                    "href": mention.actor_uri,
                    "name": "@" + mention.handle,
                    "type": "Mention",
                }
            )
            value["cc"].append(mention.actor_uri)
        # Attachments
        for attachment in self.attachments.all():
            value["attachment"].append(attachment.to_ap())
        # Remove fields if they're empty
        for field in ["cc", "tag", "attachment"]:
            if not value[field]:
                del value[field]
        return value

    def to_create_ap(self):
        """
        Returns the AP JSON to create this object
        """
        object = self.to_ap()
        return {
            "to": object["to"],
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
            "to": object["to"],
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
            "to": object["to"],
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
    def by_ap(cls, data, create=False, update=False) -> "Post":
        """
        Retrieves a Post instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises KeyError if it's not found and create is False.
        """
        # Do we have one with the right ID?
        created = False
        try:
            post = cls.objects.get(object_uri=data["id"])
        except cls.DoesNotExist:
            if create:
                # Resolve the author
                author = Identity.by_actor_uri(data["attributedTo"], create=create)
                post = cls.objects.create(
                    object_uri=data["id"],
                    author=author,
                    content=data["content"],
                    local=False,
                )
                created = True
            else:
                raise KeyError(f"No post with ID {data['id']}", data)
        if update or created:
            post.content = data["content"]
            post.summary = data.get("summary")
            post.sensitive = data.get("as:sensitive", False)
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
                elif tag["type"].lower() == "as:hashtag":
                    post.hashtags.append(tag["name"].lstrip("#"))
                elif tag["type"].lower() == "http://joinmastodon.org/ns#emoji":
                    # TODO: Handle incoming emoji
                    pass
                else:
                    raise ValueError(f"Unknown tag type {tag['type']}")
            # Visibility and to
            # (a post is public if it's ever to/cc as:Public, otherwise we
            # regard it as unlisted for now)
            targets = get_list(data, "to") + get_list(data, "cc")
            post.visibility = Post.Visibilities.unlisted
            for target in targets:
                if target.lower() == "as:public":
                    post.visibility = Post.Visibilities.public
            # Attachments
            # These have no IDs, so we have to wipe them each time
            post.attachments.all().delete()
            for attachment in get_list(data, "attachment"):
                if "http://joinmastodon.org/ns#focalPoint" in attachment:
                    focal_x, focal_y = attachment[
                        "http://joinmastodon.org/ns#focalPoint"
                    ]["@list"]
                else:
                    focal_x, focal_y = None, None
                post.attachments.create(
                    remote_url=attachment["url"],
                    mimetype=attachment["mediaType"],
                    name=attachment.get("name"),
                    width=attachment.get("width"),
                    height=attachment.get("height"),
                    blurhash=attachment.get("http://joinmastodon.org/ns#blurhash"),
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
                except (httpx.RequestError, httpx.ConnectError):
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
            cls.by_ap(data["object"], create=False, update=True)

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

    def debug_fetch(self):
        """
        Fetches the Post from its original URL again and updates us with it
        """
        response = httpx.get(
            self.object_uri,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        if 200 <= response.status_code < 300:
            return self.by_ap(
                canonicalise(response.json(), include_security=True),
                update=True,
            )
