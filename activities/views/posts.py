from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django.views.generic import TemplateView

from activities.models import Post, PostStates
from activities.services import PostService
from core.decorators import cache_page_by_ap_json
from core.ld import canonicalise
from users.models import Identity
from users.shortcuts import by_handle_or_404


@method_decorator(
    cache_page_by_ap_json("cache_timeout_page_post", public_only=True), name="dispatch"
)
@method_decorator(vary_on_headers("Accept"), name="dispatch")
class Individual(TemplateView):
    template_name = "activities/post.html"

    identity: Identity
    post_obj: Post

    def get(self, request, handle, post_id):
        self.identity = by_handle_or_404(self.request, handle, local=False)
        if self.identity.blocked:
            raise Http404("Blocked user")
        self.post_obj = get_object_or_404(
            PostService.queryset()
            .filter(author=self.identity)
            .unlisted(include_replies=True),
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
            identity=None, num_ancestors=2
        )

        context.update(
            {
                "identity": self.identity,
                "post": self.post_obj,
                "link_original": True,
                "ancestors": ancestors,
                "descendants": descendants,
                "public_styling": True,
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
