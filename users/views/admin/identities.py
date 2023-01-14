from django import forms
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from users.decorators import moderator_required
from users.models import Identity, IdentityStates


@method_decorator(moderator_required, name="dispatch")
class IdentitiesRoot(ListView):

    template_name = "admin/identities.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.query = request.GET.get("query")
        self.local_only = request.GET.get("local_only")
        self.extra_context = {
            "section": "identities",
            "query": self.query or "",
            "local_only": self.local_only,
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        identities = (
            Identity.objects.annotate(num_users=models.Count("users"))
            .annotate(followers_count=models.Count("inbound_follows"))
            .order_by("created")
        )
        if self.local_only:
            identities = identities.filter(local=True)
        if self.query:
            query = self.query.lower().strip().lstrip("@")
            if "@" in query:
                username, domain = query.split("@", 1)
                identities = identities.filter(
                    username__iexact=username,
                    domain__domain__istartswith=domain,
                )
            else:
                identities = identities.filter(
                    models.Q(username__icontains=self.query)
                    | models.Q(name__icontains=self.query)
                )
        return identities


@method_decorator(moderator_required, name="dispatch")
class IdentityEdit(FormView):

    template_name = "admin/identity_edit.html"
    extra_context = {
        "section": "identities",
    }

    class form_class(forms.Form):
        notes = forms.CharField(widget=forms.Textarea, required=False)

    def dispatch(self, request, id, *args, **kwargs):
        self.identity = get_object_or_404(Identity, id=id)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "fetch" in request.POST:
            self.identity.transition_perform(IdentityStates.outdated)
            self.identity = Identity.objects.get(pk=self.identity.pk)
        if "limit" in request.POST:
            self.identity.restriction = Identity.Restriction.limited
            self.identity.save()
        if "block" in request.POST:
            self.identity.restriction = Identity.Restriction.blocked
            self.identity.save()
        if "unlimit" in request.POST or "unblock" in request.POST:
            self.identity.restriction = Identity.Restriction.none
            self.identity.save()
        return super().post(request, *args, **kwargs)

    def get_initial(self):
        return {"notes": self.identity.admin_notes}

    def form_valid(self, form):
        self.identity.admin_notes = form.cleaned_data["notes"]
        self.identity.save()
        return redirect(".")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["identity"] = self.identity
        return context
