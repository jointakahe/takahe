from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.generic import ListView

from users.decorators import identity_required
from users.models import Follow, FollowStates


@method_decorator(identity_required, name="dispatch")
class Follows(ListView):
    """
    Shows followers/follows.
    """

    template_name = "activities/follows.html"
    extra_context = {
        "section": "follows",
    }
    paginate_by = 50

    def get_queryset(self):
        return Follow.objects.filter(
            Q(source=self.request.identity) | Q(target=self.request.identity),
            state__in=FollowStates.group_active(),
        ).order_by("-created")

    def get_context_data(self):
        context = super().get_context_data()
        identities = []
        for follow in context["page_obj"].object_list:
            if follow.source == self.request.identity:
                identity = follow.target
                follow_type = "outbound"
            else:
                identity = follow.source
                follow_type = "inbound"
            identities.append((identity, follow_type))
        context["page_obj"].object_list = identities
        return context
