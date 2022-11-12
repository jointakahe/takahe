from typing import Dict

import urlman
from django.db import models
from django.utils import timezone

from activities.models.fan_out import FanOut
from activities.models.timeline_event import TimelineEvent
from core.html import sanitize_post
from core.ld import format_date
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
        await instance.afan_out()
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
        on_delete=models.PROTECT,
        related_name="posts",
    )

    # The state the post is in
    state = StateField(PostStates)

    # If it is our post or not
    local = models.BooleanField()

    # The canonical object ID
    object_uri = models.CharField(max_length=500, blank=True, null=True)

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

    # When the post was originally created (as opposed to when we received it)
    authored = models.DateTimeField(default=timezone.now)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class urls(urlman.Urls):
        view = "{self.author.urls.view}posts/{self.id}/"
        object_uri = "{self.author.urls.actor}posts/{self.id}/"

        def get_scheme(self, url):
            return "https"

        def get_hostname(self, url):
            return self.instance.author.domain.uri_domain

    def __str__(self):
        return f"{self.author} #{self.id}"

    @property
    def safe_content(self):
        return sanitize_post(self.content)

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await Post.objects.select_related("author", "author__domain").aget(
            pk=self.pk
        )

    ### Local creation ###

    @classmethod
    def create_local(cls, author: Identity, content: str) -> "Post":
        post = cls.objects.create(
            author=author,
            content=content,
            local=True,
        )
        post.object_uri = post.author.actor_uri + f"posts/{post.id}/"
        post.url = post.object_uri
        post.save()
        return post

    ### ActivityPub (outbound) ###

    async def afan_out(self):
        """
        Creates FanOuts for a new post
        """
        # Send a copy to all people who follow this user
        post = await self.afetch_full()
        async for follow in post.author.inbound_follows.all():
            await FanOut.objects.acreate(
                identity_id=follow.source_id,
                type=FanOut.Types.post,
                subject_post=post,
            )
        # And one for themselves
        await FanOut.objects.acreate(
            identity_id=post.author_id,
            type=FanOut.Types.post,
            subject_post=post,
        )

    def to_ap(self) -> Dict:
        """
        Returns the AP JSON for this object
        """
        value = {
            "type": "Note",
            "id": self.object_uri,
            "published": format_date(self.created),
            "attributedTo": self.author.actor_uri,
            "content": self.safe_content,
            "to": "as:Public",
            "as:sensitive": self.sensitive,
            "url": self.urls.view.full(),  # type: ignore
        }
        if self.summary:
            value["summary"] = self.summary
        return value

    def to_create_ap(self):
        """
        Returns the AP JSON to create this object
        """
        return {
            "type": "Create",
            "id": self.object_uri + "#create",
            "actor": self.author.actor_uri,
            "object": self.to_ap(),
        }

    ### ActivityPub (inbound) ###

    @classmethod
    def by_ap(cls, data, create=False) -> "Post":
        """
        Retrieves a Post instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises KeyError if it's not found and create is False.
        """
        # Do we have one with the right ID?
        try:
            return cls.objects.get(object_uri=data["id"])
        except cls.DoesNotExist:
            if create:
                # Resolve the author
                author = Identity.by_actor_uri(data["attributedTo"], create=create)
                return cls.objects.create(
                    author=author,
                    content=sanitize_post(data["content"]),
                    summary=data.get("summary", None),
                    sensitive=data.get("as:sensitive", False),
                    url=data.get("url", None),
                    local=False,
                    # TODO: to
                    # TODO: mentions
                    # TODO: visibility
                )
            else:
                raise KeyError(f"No post with ID {data['id']}", data)

    @classmethod
    def handle_create_ap(cls, data):
        """
        Handles an incoming create request
        """
        # Ensure the Create actor is the Post's attributedTo
        if data["actor"] != data["object"]["attributedTo"]:
            raise ValueError("Create actor does not match its Post object", data)
        # Create it
        post = cls.by_ap(data["object"], create=True)
        # Make timeline events as appropriate
        for follow in Follow.objects.filter(target=post.author, source__local=True):
            TimelineEvent.add_post(follow.source, post)
        # Force it into fanned_out as it's not ours
        post.transition_perform(PostStates.fanned_out)
