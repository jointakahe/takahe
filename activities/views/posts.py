from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View

from activities.models import Post, PostInteraction, PostInteractionStates, PostStates
from core.ld import canonicalise
from users.decorators import identity_required
from users.shortcuts import by_handle_or_404


class Individual(TemplateView):

    template_name = "activities/post.html"

    def get(self, request, handle, post_id):
        self.identity = by_handle_or_404(self.request, handle, local=False)
        self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)
        # If they're coming in looking for JSON, they want the actor
        accept = request.META.get("HTTP_ACCEPT", "text/html").lower()
        if (
            "application/json" in accept
            or "application/ld" in accept
            or "application/activity" in accept
        ):
            # Return post JSON
            return self.serve_object()
        else:
            # Show normal page
            return super().get(request)

    def get_context_data(self):
        if self.post_obj.in_reply_to:
            try:
                parent = Post.by_object_uri(self.post_obj.in_reply_to, fetch=True)
            except Post.DoesNotExist:
                parent = None
        return {
            "identity": self.identity,
            "post": self.post_obj,
            "interactions": PostInteraction.get_post_interactions(
                [self.post_obj],
                self.request.identity,
            ),
            "link_original": True,
            "parent": parent,
            "replies": Post.objects.filter(
                models.Q(
                    visibility__in=[
                        Post.Visibilities.public,
                        Post.Visibilities.local_only,
                        Post.Visibilities.unlisted,
                    ]
                )
                | models.Q(
                    visibility=Post.Visibilities.followers,
                    author__inbound_follows__source=self.identity,
                )
                | models.Q(
                    visibility=Post.Visibilities.mentioned,
                    mentions=self.identity,
                ),
                in_reply_to=self.post_obj.object_uri,
            )
            .distinct()
            .order_by("published", "created"),
        }

    def serve_object(self):
        # If this not a local post, redirect to its canonical URI
        if not self.post_obj.local:
            return redirect(self.post_obj.object_uri)
        return JsonResponse(
            canonicalise(self.post_obj.to_ap(), include_security=True),
            content_type="application/activity+json",
        )


@method_decorator(identity_required, name="dispatch")
class Like(View):
    """
    Adds/removes a like from the current identity to the post
    """

    undo = False

    def post(self, request, handle, post_id):
        identity = by_handle_or_404(self.request, handle, local=False)
        post = get_object_or_404(
            identity.posts.prefetch_related("attachments"), pk=post_id
        )
        if self.undo:
            # Undo any likes on the post
            for interaction in PostInteraction.objects.filter(
                type=PostInteraction.Types.like,
                identity=request.identity,
                post=post,
            ):
                interaction.transition_perform(PostInteractionStates.undone)
        else:
            # Make a like on this post if we didn't already
            PostInteraction.objects.get_or_create(
                type=PostInteraction.Types.like,
                identity=request.identity,
                post=post,
            )
        # Return either a redirect or a HTMX snippet
        if request.htmx:
            return render(
                request,
                "activities/_like.html",
                {
                    "post": post,
                    "interactions": {"like": set() if self.undo else {post.pk}},
                },
            )
        return redirect(post.urls.view)


@method_decorator(identity_required, name="dispatch")
class Boost(View):
    """
    Adds/removes a boost from the current identity to the post
    """

    undo = False

    def post(self, request, handle, post_id):
        identity = by_handle_or_404(self.request, handle, local=False)
        post = get_object_or_404(identity.posts, pk=post_id)
        if self.undo:
            # Undo any boosts on the post
            for interaction in PostInteraction.objects.filter(
                type=PostInteraction.Types.boost,
                identity=request.identity,
                post=post,
            ):
                interaction.transition_perform(PostInteractionStates.undone)
        else:
            # Make a boost on this post if we didn't already
            PostInteraction.objects.get_or_create(
                type=PostInteraction.Types.boost,
                identity=request.identity,
                post=post,
            )
        # Return either a redirect or a HTMX snippet
        if request.htmx:
            return render(
                request,
                "activities/_boost.html",
                {
                    "post": post,
                    "interactions": {"boost": set() if self.undo else {post.pk}},
                },
            )
        return redirect(post.urls.view)


@method_decorator(identity_required, name="dispatch")
class Delete(TemplateView):
    """
    Deletes a post
    """

    template_name = "activities/post_delete.html"

    def dispatch(self, request, handle, post_id):
        # Make sure the request identity owns the post!
        if handle != request.identity.handle:
            raise PermissionDenied("Post author is not requestor")
        self.identity = by_handle_or_404(self.request, handle, local=False)
        self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)
        return super().dispatch(request)

    def get_context_data(self):
        return {"post": self.post_obj}

    def post(self, request):
        self.post_obj.transition_perform(PostStates.deleted)
        return redirect("/")
