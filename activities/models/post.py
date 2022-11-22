import re
from typing import Dict, Optional

import httpx
import urlman
from django.db import models, transaction
from django.template.defaultfilters import linebreaks_filter
from django.utils import timezone
from django.utils.safestring import mark_safe

from activities.models.fan_out import FanOut
from activities.models.timeline_event import TimelineEvent
from core.html import sanitize_post, strip_html
from core.ld import canonicalise, format_ld_date, get_list, parse_ld_date
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.follow import Follow
from users.models.identity import Identity


class PostStates(StateGraph):
    new = State(try_interval=300)
    fanned_out = State()

    new.transitions_to(fanned_out)

    @classmethod
    async def handle_new(cls, instance: "Post"):
        """
        Creates all needed fan-out objects for a new Post.
        """
        post = await instance.afetch_full()
        # Non-local posts should not be here
        # TODO: This seems to keep happening. Work out how?
        if not post.local:
            print(f"Trying to run handle_new on a non-local post {post.pk}!")
            return cls.fanned_out
        # Build list of targets - mentions always included
        targets = set()
        async for mention in post.mentions.all():
            targets.add(mention)
        # Then, if it's not mentions only, also deliver to followers
        if post.visibility != Post.Visibilities.mentioned:
            async for follower in post.author.inbound_follows.select_related("source"):
                targets.add(follower.source)
        # Fan out to each one
        for follow in targets:
            await FanOut.objects.acreate(
                identity=follow,
                type=FanOut.Types.post,
                subject_post=post,
            )
        # And one for themselves if they're local
        if post.author.local:
            await FanOut.objects.acreate(
                identity_id=post.author_id,
                type=FanOut.Types.post,
                subject_post=post,
            )
        return cls.fanned_out


class Post(StatorModel):
    """
    A post (status, toot) that is either local or remote.
    """

    class Visibilities(models.IntegerChoices):
        public = 0
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

    class urls(urlman.Urls):
        view = "{self.author.urls.view}posts/{self.id}/"
        object_uri = "{self.author.actor_uri}posts/{self.id}/"
        action_like = "{view}like/"
        action_unlike = "{view}unlike/"
        action_boost = "{view}boost/"
        action_unboost = "{view}unboost/"

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

    ### Content cleanup and extraction ###

    mention_regex = re.compile(
        r"([^\w\d\-_])@([\w\d\-_]+(?:@[\w\d\-_]+\.[\w\d\-_\.]+)?)"
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

        def replacer(match):
            precursor = match.group(1)
            handle = match.group(2)
            if handle in possible_matches:
                return f'{precursor}<a href="{possible_matches[handle]}">@{handle}</a>'
            else:
                return match.group()

        return mark_safe(self.mention_regex.sub(replacer, content))

    def safe_content_local(self):
        """
        Returns the content formatted for local display
        """
        return self.linkify_mentions(sanitize_post(self.content), local=True)

    def safe_content_remote(self):
        """
        Returns the content formatted for remote consumption
        """
        return self.linkify_mentions(sanitize_post(self.content))

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return (
            await Post.objects.select_related("author", "author__domain")
            .prefetch_related("mentions", "mentions__domain")
            .aget(pk=self.pk)
        )

    ### Local creation ###

    @classmethod
    def create_local(
        cls,
        author: Identity,
        content: str,
        summary: Optional[str] = None,
        visibility: int = Visibilities.public,
    ) -> "Post":
        with transaction.atomic():
            # Find mentions in this post
            mention_hits = cls.mention_regex.findall(content)
            mentions = set()
            for precursor, handle in mention_hits:
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
            )
            post.object_uri = post.urls.object_uri
            post.url = post.absolute_object_uri()
            post.mentions.set(mentions)
            post.save()
        return post

    ### ActivityPub (outbound) ###

    def to_ap(self) -> Dict:
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
        }
        if self.summary:
            value["summary"] = self.summary
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
        # Remove tag and cc if they're empty
        if not value["cc"]:
            del value["cc"]
        if not value["tag"]:
            del value["tag"]
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
                # Go grab the data from the URI
                response = httpx.get(
                    object_uri,
                    headers={"Accept": "application/json"},
                    follow_redirects=True,
                )
                if 200 <= response.status_code < 300:
                    return cls.by_ap(
                        canonicalise(response.json(), include_security=True),
                        create=True,
                        update=True,
                    )
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
            # Create it
            post = cls.by_ap(data["object"], create=True, update=True)
            # Make timeline events for followers if it's not a reply
            # TODO: _do_ show replies to people we follow somehow
            if not post.in_reply_to:
                for follow in Follow.objects.filter(
                    target=post.author, source__local=True
                ):
                    TimelineEvent.add_post(follow.source, post)
            # Make timeline events for mentions if they're local
            for mention in post.mentions.all():
                if mention.local:
                    TimelineEvent.add_mentioned(mention, post)
            # Force it into fanned_out as it's not ours
            post.transition_perform(PostStates.fanned_out)

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
        Handles an incoming create request
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
