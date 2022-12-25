from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django.views.generic import TemplateView, View

from activities.models import PostInteraction, PostStates
from activities.services import PostService
from core.decorators import cache_page_by_ap_json
from core.ld import canonicalise
from users.decorators import identity_required
from users.shortcuts import by_handle_or_404


@method_decorator(
    cache_page_by_ap_json("cache_timeout_page_post", public_only=True), name="dispatch"
)
@method_decorator(vary_on_headers("Accept"), name="dispatch")
class Individual(TemplateView):

    template_name = "activities/post.html"

    def get(self, request, handle, post_id):
        self.identity = by_handle_or_404(self.request, handle, local=False)
        if self.identity.blocked:
            raise Http404("Blocked user")
        self.post_obj = get_object_or_404(
            PostService.queryset().filter(author=self.identity),
            pk=post_id,
        )
        if self.post_obj.state in [PostStates.deleted, PostStates.deleted_fanned_out]:
            raise Http404("Deleted post")
        # If they're coming in looking for JSON, they want the actor
        if request.ap_json:
            # Return post JSON
            return self.serve_object()
        else:
            # Show normal page
            return super().get(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ancestors, descendants = PostService(self.post_obj).context(
            self.request.identity
        )

        context.update(
            {
                "identity": self.identity,
                "post": self.post_obj,
                "interactions": PostInteraction.get_post_interactions(
                    [self.post_obj] + ancestors + descendants,
                    self.request.identity,
                ),
                "link_original": True,
                "ancestors": ancestors,
                "descendants": descendants,
            }
        )

        return context

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
            PostService.queryset().filter(author=identity),
            pk=post_id,
        )
        service = PostService(post)
        if self.undo:
            service.unlike_as(request.identity)
            post.like_count = max(0, post.like_count - 1)
        else:
            service.like_as(request.identity)
            post.like_count += 1
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
        post = get_object_or_404(
            PostService.queryset().filter(author=identity),
            pk=post_id,
        )
        service = PostService(post)
        if self.undo:
            service.unboost_as(request.identity)
            post.boost_count = max(0, post.boost_count - 1)
        else:
            service.boost_as(request.identity)
            post.boost_count += 1
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
