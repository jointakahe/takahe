from django import forms
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from users.decorators import admin_required
from users.models import Domain


@method_decorator(admin_required, name="dispatch")
class FederationRoot(ListView):

    template_name = "admin/federation.html"
    paginate_by = 50

    def get(self, request, *args, **kwargs):
        self.query = request.GET.get("query")
        self.extra_context = {
            "section": "federation",
            "query": self.query or "",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        domains = (
            Domain.objects.filter(local=False)
            .annotate(num_users=models.Count("identities"))
            .order_by("domain")
        )
        if self.query:
            domains = domains.filter(domain__icontains=self.query)
        return domains


@method_decorator(admin_required, name="dispatch")
class FederationEdit(FormView):

    template_name = "admin/federation_edit.html"
    extra_context = {"section": "federation"}

    class form_class(forms.Form):
        blocked = forms.BooleanField(
            help_text="If this domain is blocked from interacting with this server.\nAll incoming posts from this domain will be irrecoverably dropped.",
            widget=forms.Select(choices=[(True, "Blocked"), (False, "Not Blocked")]),
            required=False,
        )
        notes = forms.CharField(
            label="Notes",
            widget=forms.Textarea(
                attrs={
                    "rows": 3,
                },
            ),
            required=False,
        )

    def dispatch(self, request, domain):
        self.domain = get_object_or_404(
            Domain.objects.filter(local=False), domain=domain
        )
        return super().dispatch(request)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["domain"] = self.domain
        return context

    def form_valid(self, form):
        self.domain.blocked = form.cleaned_data["blocked"]
        self.domain.notes = form.cleaned_data["notes"] or None
        self.domain.save()
        return redirect(Domain.urls.root_federation)

    def get_initial(self):
        return {
            "blocked": self.domain.blocked,
            "notes": self.domain.notes,
        }
