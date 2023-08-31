from django.db import models
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import ListView

from users.decorators import admin_required
from users.models import Identity, RelayActor


@method_decorator(admin_required, name="dispatch")
class RelayRoot(ListView):
    template_name = "admin/relays.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.extra_context = {
            "section": "relays",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        identities = (
            Identity.objects.filter(inbound_follows__source=RelayActor.get_identity())
            .annotate(follow_state=models.F("inbound_follows__state"))
            .order_by("-created")
        )
        return identities

    def post(self, request, *args, **kwargs):
        actor_uri = request.POST.get("actor_uri")
        if "subscribe" in request.GET:
            RelayActor.subscribe(actor_uri)
        elif "unsubscribe" in request.GET:
            RelayActor.unsubscribe(actor_uri)
        elif "remove" in request.GET:
            RelayActor.remove(actor_uri)
        return redirect(".")
