from collections.abc import Iterable

from django.db import models, transaction
from django.utils import timezone

from activities.models.fan_out import FanOut
from activities.models.post import Post
from activities.models.post_types import QuestionData
from core.ld import format_ld_date, get_str_or_id, parse_ld_date
from core.snowflake import Snowflake
from stator.models import State, StateField, StateGraph, StatorModel
from users.models.identity import Identity


class PostInteractionStates(StateGraph):
    new = State(try_interval=300)
    fanned_out = State(externally_progressed=True)
    undone = State(try_interval=300)
    undone_fanned_out = State(delete_after=24 * 60 * 60)

    new.transitions_to(fanned_out)
    fanned_out.transitions_to(undone)
    undone.transitions_to(undone_fanned_out)

    @classmethod
    def group_active(cls):
        return [cls.new, cls.fanned_out]

    @classmethod
    async def handle_new(cls, instance: "PostInteraction"):
        """
        Creates all needed fan-out objects for a new PostInteraction.
        """
        interaction = await instance.afetch_full()
        # Boost: send a copy to all people who follow this user (limiting
        # to just local follows if it's a remote boost)
        # Pin: send Add activity to all people who follow this user
        if (
            interaction.type == interaction.Types.boost
            or interaction.type == interaction.Types.pin
        ):
            for target in await interaction.aget_targets():
                await FanOut.objects.acreate(
                    type=FanOut.Types.interaction,
                    identity=target,
                    subject_post=interaction.post,
                    subject_post_interaction=interaction,
                )
        # Like: send a copy to the original post author only,
        # if the liker is local or they are
        elif interaction.type == interaction.Types.like:
            if interaction.identity.local or interaction.post.local:
                await FanOut.objects.acreate(
                    type=FanOut.Types.interaction,
                    identity_id=interaction.post.author_id,
                    subject_post=interaction.post,
                    subject_post_interaction=interaction,
                )
        # Vote: send a copy of the vote to the original
        # post author only if it's a local interaction
        # to a non local post
        elif interaction.type == interaction.Types.vote:
            if interaction.identity.local and not interaction.post.local:
                await FanOut.objects.acreate(
                    type=FanOut.Types.interaction,
                    identity_id=interaction.post.author_id,
                    subject_post=interaction.post,
                    subject_post_interaction=interaction,
                )
        else:
            raise ValueError("Cannot fan out unknown type")
        # And one for themselves if they're local and it's a boost
        if (
            interaction.type == PostInteraction.Types.boost
            and interaction.identity.local
        ):
            await FanOut.objects.acreate(
                identity_id=interaction.identity_id,
                type=FanOut.Types.interaction,
                subject_post=interaction.post,
                subject_post_interaction=interaction,
            )
        return cls.fanned_out

    @classmethod
    async def handle_undone(cls, instance: "PostInteraction"):
        """
        Creates all needed fan-out objects to undo a PostInteraction.
        """
        interaction = await instance.afetch_full()
        # Undo Boost: send a copy to all people who follow this user
        # Undo Pin: send a Remove activity to all people who follow this user
        if (
            interaction.type == interaction.Types.boost
            or interaction.type == interaction.Types.pin
        ):
            async for follow in interaction.identity.inbound_follows.select_related(
                "source", "target"
            ):
                if follow.source.local or follow.target.local:
                    await FanOut.objects.acreate(
                        type=FanOut.Types.undo_interaction,
                        identity_id=follow.source_id,
                        subject_post=interaction.post,
                        subject_post_interaction=interaction,
                    )
        # Undo Like: send a copy to the original post author only
        elif interaction.type == interaction.Types.like:
            await FanOut.objects.acreate(
                type=FanOut.Types.undo_interaction,
                identity_id=interaction.post.author_id,
                subject_post=interaction.post,
                subject_post_interaction=interaction,
            )
        else:
            raise ValueError("Cannot fan out unknown type")
        # And one for themselves if they're local and it's a boost
        if (
            interaction.type == PostInteraction.Types.boost
            and interaction.identity.local
        ):
            await FanOut.objects.acreate(
                identity_id=interaction.identity_id,
                type=FanOut.Types.undo_interaction,
                subject_post=interaction.post,
                subject_post_interaction=interaction,
            )
        return cls.undone_fanned_out


class PostInteraction(StatorModel):
    """
    Handles both boosts and likes
    """

    class Types(models.TextChoices):
        like = "like"
        boost = "boost"
        vote = "vote"
        pin = "pin"

    id = models.BigIntegerField(
        primary_key=True,
        default=Snowflake.generate_post_interaction,
    )

    # The state the boost is in
    state = StateField(PostInteractionStates)

    # The canonical object ID
    object_uri = models.CharField(max_length=500, blank=True, null=True, unique=True)

    # What type of interaction it is
    type = models.CharField(max_length=100, choices=Types.choices)

    # The user who boosted/liked/etc.
    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="interactions",
    )

    # The post that was boosted/liked/etc
    post = models.ForeignKey(
        "activities.Post",
        on_delete=models.CASCADE,
        related_name="interactions",
    )

    # Used to store any interaction extra text value like the vote
    # in the question/poll case
    value = models.CharField(max_length=50, blank=True, null=True)

    # When the activity was originally created (as opposed to when we received it)
    # Mastodon only seems to send this for boosts, not likes
    published = models.DateTimeField(default=timezone.now)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["type", "identity", "post"])]

    ### Display helpers ###

    @classmethod
    def get_post_interactions(cls, posts, identity):
        """
        Returns a dict of {interaction_type: set(post_ids)} for all the posts
        and the given identity, for use in templates.
        """
        # Bulk-fetch any of our own interactions
        ids_with_interaction_type = cls.objects.filter(
            identity=identity,
            post_id__in=[post.pk for post in posts],
            type__in=[cls.Types.like, cls.Types.boost, cls.Types.pin],
            state__in=[PostInteractionStates.new, PostInteractionStates.fanned_out],
        ).values_list("post_id", "type")
        # Make it into the return dict
        result = {}
        for post_id, interaction_type in ids_with_interaction_type:
            result.setdefault(interaction_type, set()).add(post_id)
        return result

    @classmethod
    def get_event_interactions(cls, events, identity) -> dict[str, set[str]]:
        """
        Returns a dict of {interaction_type: set(post_ids)} for all the posts
        within the events and the given identity, for use in templates.
        """
        return cls.get_post_interactions(
            [e.subject_post for e in events if e.subject_post], identity
        )

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await PostInteraction.objects.select_related(
            "identity", "post", "post__author"
        ).aget(pk=self.pk)

    async def aget_targets(self) -> Iterable[Identity]:
        """
        Returns an iterable with Identities of followers that have unique
        shared_inbox among each other to be used as target.

        When interaction is boost, only boost follows are considered,
        for pins all followers are considered.
        """
        # Start including the post author
        targets = {self.post.author}

        query = self.identity.inbound_follows.active()
        # Include all followers that are following the boosts
        if self.type == self.Types.boost:
            query = query.filter(boosts=True)
        async for follow in query.select_related("source"):
            targets.add(follow.source)

        # Fetch the full blocks and remove them as targets
        async for block in self.identity.outbound_blocks.active().filter(
            mute=False
        ).select_related("target"):
            try:
                targets.remove(block.target)
            except KeyError:
                pass

        deduped_targets = set()
        shared_inboxes = set()
        for target in targets:
            if target.local:
                # Local targets always gets the boosts
                # despite its creator locality
                deduped_targets.add(target)
            elif self.identity.local:
                # Dedupe the targets based on shared inboxes
                # (we only keep one per shared inbox)
                if not target.shared_inbox_uri:
                    deduped_targets.add(target)
                elif target.shared_inbox_uri not in shared_inboxes:
                    shared_inboxes.add(target.shared_inbox_uri)
                    deduped_targets.add(target)

        return deduped_targets

    ### Create helpers ###

    @classmethod
    def create_votes(cls, post, identity, choices) -> list["PostInteraction"]:
        question = post.type_data

        if question.end_time and timezone.now() > question.end_time:
            raise ValueError("Validation failed: The poll has already ended")

        if post.interactions.filter(identity=identity, type=cls.Types.vote).exists():
            raise ValueError("Validation failed: You have already voted on this poll")

        votes = []
        with transaction.atomic():
            for choice in set(choices):
                vote = cls.objects.create(
                    identity=identity,
                    post=post,
                    type=PostInteraction.Types.vote,
                    value=question.options[choice].name,
                )
                vote.object_uri = f"{identity.actor_uri}#votes/{vote.id}"
                vote.save()
                votes.append(vote)

                if not post.local:
                    question.options[choice].votes += 1

            if not post.local:
                question.voter_count += 1

            post.calculate_type_data()

        return votes

    ### ActivityPub (outbound) ###

    def to_ap(self) -> dict:
        """
        Returns the AP JSON for this object
        """
        # Create an object URI if we don't have one
        if self.object_uri is None:
            self.object_uri = self.identity.actor_uri + f"#{self.type}/{self.id}"
        if self.type == self.Types.boost:
            value = {
                "type": "Announce",
                "id": self.object_uri,
                "published": format_ld_date(self.published),
                "actor": self.identity.actor_uri,
                "object": self.post.object_uri,
                "to": "as:Public",
            }
        elif self.type == self.Types.like:
            value = {
                "type": "Like",
                "id": self.object_uri,
                "published": format_ld_date(self.published),
                "actor": self.identity.actor_uri,
                "object": self.post.object_uri,
            }
        elif self.type == self.Types.vote:
            value = {
                "type": "Note",
                "id": self.object_uri,
                "to": self.post.author.actor_uri,
                "name": self.value,
                "inReplyTo": self.post.object_uri,
                "attributedTo": self.identity.actor_uri,
            }
        elif self.type == self.Types.pin:
            raise ValueError("Cannot turn into AP")
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
            "id": self.object_uri,
            "actor": self.identity.actor_uri,
            "object": object,
        }

    def to_undo_ap(self) -> dict:
        """
        Returns the AP JSON to undo this object
        """
        object = self.to_ap()
        return {
            "id": object["id"] + "/undo",
            "type": "Undo",
            "actor": self.identity.actor_uri,
            "object": object,
        }

    def to_add_ap(self):
        """
        Returns the AP JSON to add a pin interaction to the featured collection
        """
        return {
            "type": "Add",
            "actor": self.identity.actor_uri,
            "object": self.post.object_uri,
            "target": self.identity.actor_uri + "collections/featured/",
        }

    def to_remove_ap(self):
        """
        Returns the AP JSON to remove a pin interaction from the featured collection
        """
        return {
            "type": "Remove",
            "actor": self.identity.actor_uri,
            "object": self.post.object_uri,
            "target": self.identity.actor_uri + "collections/featured/",
        }

    ### ActivityPub (inbound) ###

    @classmethod
    def by_ap(cls, data, create=False) -> "PostInteraction":
        """
        Retrieves a PostInteraction instance by its ActivityPub JSON object.

        Optionally creates one if it's not present.
        Raises KeyError if it's not found and create is False.
        """
        # Do we have one with the right ID?
        try:
            boost = cls.objects.get(object_uri=data["id"])
        except cls.DoesNotExist:
            if create:
                # Resolve the author
                identity = Identity.by_actor_uri(data["actor"], create=True)
                # Resolve the post
                object = data["object"]
                target = get_str_or_id(object, "inReplyTo") or get_str_or_id(object)
                post = Post.by_object_uri(target, fetch=True)
                value = None
                # Get the right type
                if data["type"].lower() == "like":
                    type = cls.Types.like
                elif data["type"].lower() == "announce":
                    type = cls.Types.boost
                elif (
                    data["type"].lower() == "create"
                    and object["type"].lower() == "note"
                    and isinstance(post.type_data, QuestionData)
                ):
                    type = cls.Types.vote
                    question = post.type_data
                    value = object["name"]
                    if question.end_time and timezone.now() > question.end_time:
                        # TODO: Maybe create an expecific expired exception?
                        raise cls.DoesNotExist(
                            f"Cannot create a vote to the expired question {post.id}"
                        )

                    already_voted = (
                        post.type_data.mode == "oneOf"
                        and post.interactions.filter(
                            type=cls.Types.vote, identity=identity
                        ).exists()
                    )
                    if already_voted:
                        raise cls.DoesNotExist(
                            f"The identity {identity.handle} already voted in question {post.id}"
                        )

                else:
                    raise ValueError(f"Cannot handle AP type {data['type']}")
                # Make the actual interaction
                boost = cls.objects.create(
                    object_uri=data["id"],
                    identity=identity,
                    post=post,
                    published=parse_ld_date(data.get("published", None))
                    or timezone.now(),
                    type=type,
                    value=value,
                )
            else:
                raise cls.DoesNotExist(f"No interaction with ID {data['id']}", data)
        return boost

    @classmethod
    def handle_ap(cls, data):
        """
        Handles an incoming announce/like
        """
        with transaction.atomic():
            # Create it
            try:
                interaction = cls.by_ap(data, create=True)
            except (cls.DoesNotExist, Post.DoesNotExist):
                # That post is gone, boss
                # TODO: Limited retry state?
                return

            interaction.post.calculate_stats()
            interaction.post.calculate_type_data()

    @classmethod
    def handle_undo_ap(cls, data):
        """
        Handles an incoming undo for a announce/like
        """
        with transaction.atomic():
            # Find it
            try:
                interaction = cls.by_ap(data["object"])
            except (cls.DoesNotExist, Post.DoesNotExist):
                # Well I guess we don't need to undo it do we
                return
            # Verify the actor matches
            if data["actor"] != interaction.identity.actor_uri:
                raise ValueError("Actor mismatch on interaction undo")
            # Delete all events that reference it
            interaction.timeline_events.all().delete()
            # Force it into undone_fanned_out as it's not ours
            interaction.transition_perform(PostInteractionStates.undone_fanned_out)
            # Recalculate post stats
            interaction.post.calculate_stats()
            interaction.post.calculate_type_data()

    @classmethod
    def handle_add_ap(cls, data):
        """
        Handles an incoming Add activity which is a pin
        """
        target = data.get("target", None)
        if not target:
            return

        # we only care about pinned posts, not hashtags
        object = data.get("object", {})
        if isinstance(object, dict) and object.get("type") == "Hashtag":
            return

        with transaction.atomic():
            identity = Identity.by_actor_uri(data["actor"], create=True)
            # it's only a pin if the target is the identity's featured collection URI
            if identity.featured_collection_uri != target:
                return

            object_uri = get_str_or_id(object)
            if not object_uri:
                return
            post = Post.by_object_uri(object_uri, fetch=True)

            return PostInteraction.objects.get_or_create(
                type=cls.Types.pin,
                identity=identity,
                post=post,
                state__in=PostInteractionStates.group_active(),
            )[0]

    @classmethod
    def handle_remove_ap(cls, data):
        """
        Handles an incoming Remove activity which is an unpin
        """
        target = data.get("target", None)
        if not target:
            return

        # we only care about pinned posts, not hashtags
        object = data.get("object", {})
        if isinstance(object, dict) and object.get("type") == "Hashtag":
            return

        with transaction.atomic():
            identity = Identity.by_actor_uri(data["actor"], create=True)
            # it's only an unpin if the target is the identity's featured collection URI
            if identity.featured_collection_uri != target:
                return

            try:
                object_uri = get_str_or_id(object)
                if not object_uri:
                    return
                post = Post.by_object_uri(object_uri, fetch=False)
                for interaction in cls.objects.filter(
                    type=cls.Types.pin,
                    identity=identity,
                    post=post,
                    state__in=PostInteractionStates.group_active(),
                ):
                    # Force it into undone_fanned_out as it's not ours
                    interaction.transition_perform(
                        PostInteractionStates.undone_fanned_out
                    )
            except (cls.DoesNotExist, Post.DoesNotExist):
                return

    ### Mastodon API ###

    def to_mastodon_status_json(self, interactions=None, identity=None):
        """
        This wraps Posts in a fake Status for boost interactions.
        """
        if self.type != self.Types.boost:
            raise ValueError(
                f"Cannot make status JSON for interaction of type {self.type}"
            )
        # Make a fake post for this boost (because mastodon treats boosts as posts)
        post_json = self.post.to_mastodon_json(
            interactions=interactions, identity=identity
        )
        return {
            "id": f"{self.pk}",
            "uri": post_json["uri"],
            "created_at": format_ld_date(self.published),
            "account": self.identity.to_mastodon_json(include_counts=False),
            "content": "",
            "visibility": post_json["visibility"],
            "sensitive": post_json["sensitive"],
            "spoiler_text": post_json["spoiler_text"],
            "media_attachments": [],
            "mentions": [],
            "tags": [],
            "emojis": [],
            "reblogs_count": 0,
            "favourites_count": 0,
            "replies_count": 0,
            "url": post_json["url"],
            "in_reply_to_id": None,
            "in_reply_to_account_id": None,
            "poll": post_json["poll"],
            "card": None,
            "language": None,
            "text": "",
            "edited_at": None,
            "reblog": post_json,
        }
