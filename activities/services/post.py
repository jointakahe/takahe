from activities.models import (
    Post,
    PostInteraction,
    PostInteractionStates,
    PostStates,
    TimelineEvent,
)
from core.exceptions import capture_message
from users.models import Identity


class PostService:
    """
    High-level operations on Posts
    """

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
        )

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
        self.post.calculate_stats()

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
        self.post.calculate_stats()

    def like_as(self, identity: Identity):
        self.interact_as(identity, PostInteraction.Types.like)

    def unlike_as(self, identity: Identity):
        self.uninteract_as(identity, PostInteraction.Types.like)

    def boost_as(self, identity: Identity):
        self.interact_as(identity, PostInteraction.Types.boost)

    def unboost_as(self, identity: Identity):
        self.uninteract_as(identity, PostInteraction.Types.boost)

    def context(
        self,
        identity: Identity | None,
        num_ancestors: int = 10,
        num_descendants: int = 50,
    ) -> tuple[list[Post], list[Post]]:
        """
        Returns ancestor/descendant information.

        Ancestors are guaranteed to be in order from closest to furthest.
        Descendants are in depth-first order, starting with closest.

        If identity is provided, includes mentions/followers-only posts they
        can see. Otherwise, shows unlisted and above only.
        """
        # Retrieve ancestors via parent walk
        ancestors: list[Post] = []
        ancestor = self.post
        while ancestor.in_reply_to and len(ancestors) < num_ancestors:
            object_uri = ancestor.in_reply_to
            reason = ancestor.object_uri
            ancestor = self.queryset().filter(object_uri=object_uri).first()
            if ancestor is None:
                try:
                    Post.ensure_object_uri(object_uri, reason=reason)
                except ValueError:
                    capture_message(
                        f"Cannot fetch ancestor Post={self.post.pk}, ancestor_uri={object_uri}"
                    )
                break
            if ancestor.state in [PostStates.deleted, PostStates.deleted_fanned_out]:
                break
            ancestors.append(ancestor)
        # Retrieve descendants via breadth-first-search
        descendants: list[Post] = []
        queue = [self.post]
        seen: set[str] = set()
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
                if child.pk not in seen:
                    descendants.append(child)
                    queue.append(child)
                    seen.add(child.pk)
        return ancestors, descendants

    def delete(self):
        """
        Marks a post as deleted and immediately cleans up its timeline events etc.
        """
        self.post.transition_perform(PostStates.deleted)
        TimelineEvent.objects.filter(subject_post=self.post).delete()
        PostInteraction.transition_perform_queryset(
            PostInteraction.objects.filter(
                post=self.post,
                state__in=PostInteractionStates.group_active(),
            ),
            PostInteractionStates.undone,
        )
