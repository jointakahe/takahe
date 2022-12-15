from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from users.decorators import identity_required
from users.models import Follow, FollowStates


@method_decorator(identity_required, name="dispatch")
class FollowsPage(TemplateView):
    """
    Shows followers/follows.
    """

    template_name = "activities/follows.html"

    def get_context_data(self):
        # Gather all identities with a following relationship with us
        follows = Follow.objects.filter(
            Q(source=self.request.identity) | Q(target=self.request.identity),
            state__in=FollowStates.group_active(),
        ).order_by("-id")
        paginator = Paginator(follows, 50)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        identities = []
        for follow in page_obj.object_list:
            if follow.source == self.request.identity:
                identity = follow.target
                follow_type = "outbound"
            else:
                identity = follow.source
                follow_type = "inbound"
            identities.append((identity, follow_type))
        page_obj.object_list = identities

        return {
            "section": "follows",
            "page_obj": page_obj,
        }
