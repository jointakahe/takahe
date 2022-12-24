from django.db import models

from activities.models import Post, PostInteraction, PostInteractionStates, PostStates
from users.models import Identity


class PostService:
    """
    High-level operations on Posts
    """

    def __init__(self, post: Post):
        self.post = post

    def interact_as(self, identity: Identity, type: str):
        """
        Performs an interaction on this Post
        """
        interaction = PostInteraction.objects.get_or_create(
            type=type,
            identity=identity,
            post=self.post,
        )[0]
        if interaction.state not in PostInteractionStates.group_active():
            interaction.transition_perform(PostInteractionStates.new)

    def uninteract_as(self, identity, type):
        """
        Undoes an interaction on this Post
        """
        for interaction in PostInteraction.objects.filter(
            type=type,
            identity=identity,
            post=self.post,
        ):
            interaction.transition_perform(PostInteractionStates.undone)

    def like_as(self, identity: Identity):
        self.interact_as(identity, PostInteraction.Types.like)

    def unlike_as(self, identity: Identity):
        self.uninteract_as(identity, PostInteraction.Types.like)

    def boost_as(self, identity: Identity):
        self.interact_as(identity, PostInteraction.Types.boost)

    def unboost_as(self, identity: Identity):
        self.uninteract_as(identity, PostInteraction.Types.boost)

    @classmethod
    def queryset(cls):
        """
        Returns the base queryset to use for fetching posts efficiently.
        """
        return (
            Post.objects.not_hidden()
            .prefetch_related(
                "attachments",
                "mentions",
                "emojis",
            )
            .select_related(
                "author",
                "author__domain",
            )
            .annotate(
                like_count=models.Count(
                    "interactions",
                    filter=models.Q(
                        interactions__type=PostInteraction.Types.like,
                        interactions__state__in=PostInteractionStates.group_active(),
                    ),
                ),
                boost_count=models.Count(
                    "interactions",
                    filter=models.Q(
                        interactions__type=PostInteraction.Types.boost,
                        interactions__state__in=PostInteractionStates.group_active(),
                    ),
                ),
            )
        )

    def context(self, identity: Identity | None) -> tuple[list[Post], list[Post]]:
        """
        Returns ancestor/descendant information.

        Ancestors are guaranteed to be in order from closest to furthest.
        Descendants are in depth-first order, starting with closest.

        If identity is provided, includes mentions/followers-only posts they
        can see. Otherwise, shows unlisted and above only.
        """
        num_ancestors = 10
        num_descendants = 50
        # Retrieve ancestors via parent walk
        ancestors: list[Post] = []
        ancestor = self.post
        while ancestor.in_reply_to and len(ancestors) < num_ancestors:
            ancestor = self.queryset().get(object_uri=ancestor.in_reply_to)
            if ancestor is None:
                break
            if ancestor.state in [PostStates.deleted, PostStates.deleted_fanned_out]:
                break
            ancestors.append(ancestor)
        # Retrieve descendants via breadth-first-search
        descendants: list[Post] = []
        queue = [self.post]
        while queue and len(descendants) < num_descendants:
            node = queue.pop()
            child_queryset = (
                self.queryset()
                .filter(in_reply_to=node.object_uri)
                .order_by("published")
            )
            if identity:
                child_queryset = child_queryset.visible_to(
                    identity=identity, include_replies=True
                )
            else:
                child_queryset = child_queryset.unlisted(include_replies=True)
            for child in child_queryset:
                descendants.append(child)
                queue.append(child)
        return ancestors, descendants
