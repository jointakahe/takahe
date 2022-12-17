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

    def get(self, request, *args, **kwargs):
        self.inbound = self.request.GET.get("inbound")
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if self.inbound:
            return Follow.objects.filter(
                target=self.request.identity,
                state__in=FollowStates.group_active(),
            ).order_by("-created")
        else:
            return Follow.objects.filter(
                source=self.request.identity,
                state__in=FollowStates.group_active(),
            ).order_by("-created")

    def get_context_data(self):
        context = super().get_context_data()
        # Go work out if any of these people also follow us/are followed
        if self.inbound:
            context["page_obj"].object_list = [
                follow.source for follow in context["page_obj"]
            ]
            identity_ids = [identity.id for identity in context["page_obj"]]
            context["outbound_ids"] = Follow.objects.filter(
                source=self.request.identity, target_id__in=identity_ids
            ).values_list("target_id", flat=True)
        else:
            context["page_obj"].object_list = [
                follow.target for follow in context["page_obj"]
            ]
            identity_ids = [identity.id for identity in context["page_obj"]]
            context["inbound_ids"] = Follow.objects.filter(
                target=self.request.identity, source_id__in=identity_ids
            ).values_list("source_id", flat=True)
        context["inbound"] = self.inbound
        context["num_inbound"] = Follow.objects.filter(
            target=self.request.identity,
            state__in=FollowStates.group_active(),
        ).count()
        context["num_outbound"] = Follow.objects.filter(
            source=self.request.identity,
            state__in=FollowStates.group_active(),
        ).count()
        return context
