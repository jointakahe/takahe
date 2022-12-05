from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from core.decorators import per_identity_cache_page
from users.decorators import identity_required
from users.models import FollowStates


@method_decorator(identity_required, name="dispatch")
@method_decorator(
    per_identity_cache_page("cache_timeout_page_timeline"), name="dispatch"
)
class FollowsPage(TemplateView):
    """
    Shows followers/follows.
    """

    template_name = "activities/follows.html"

    def get_context_data(self):
        # Gather all identities with a following relationship with us
        identities = {}
        for outbound_follow in self.request.identity.outbound_follows.filter(
            state__in=FollowStates.group_active()
        ):
            identities.setdefault(outbound_follow.target, {})[
                "outbound"
            ] = outbound_follow
        for inbound_follow in self.request.identity.inbound_follows.filter(
            state__in=FollowStates.group_active()
        ):
            identities.setdefault(inbound_follow.source, {})["inbound"] = inbound_follow

        return {
            "section": "follows",
            "identities": sorted(identities.items(), key=lambda i: i[0].username),
        }
