from django import forms
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from users.decorators import admin_required
from users.models import Domain


@method_decorator(admin_required, name="dispatch")
class FederationRoot(TemplateView):

    template_name = "admin/federation.html"

    def get_context_data(self):
        return {
            "domains": Domain.objects.filter(local=False)
            .annotate(num_users=models.Count("identities"))
            .order_by("domain"),
            "section": "federation",
        }


@method_decorator(admin_required, name="dispatch")
class FederationEdit(FormView):

    template_name = "admin/federation_edit.html"
    extra_context = {"section": "federation"}

    class form_class(forms.Form):
        blocked = forms.BooleanField(
            help_text="If this domain is blocked from interacting with this server",
            widget=forms.Select(choices=[(True, "Blocked"), (False, "Not Blocked")]),
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
        self.domain.save()
        return redirect(Domain.urls.root_federation)

    def get_initial(self):
        return {
            "blocked": self.domain.blocked,
        }
