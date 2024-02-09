from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import ListView

from users.decorators import admin_required
from users.models import Relay


@method_decorator(admin_required, name="dispatch")
class RelaysRoot(ListView):
    template_name = "admin/relays.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.extra_context = {
            "section": "relays",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Relay.objects.all().order_by("-id")

    def post(self, request, *args, **kwargs):
        if "subscribe" in request.GET:
            Relay.subscribe(request.POST.get("inbox_uri"))
        elif "unsubscribe" in request.GET:
            Relay.objects.get(pk=int(request.POST.get("id"))).unsubscribe()
        elif "remove" in request.GET:
            Relay.objects.get(pk=int(request.POST.get("id"))).force_unsubscribe()
        return redirect(".")
