from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from users.models import Identity
from users.views.base import IdentityViewMixin


@method_decorator(login_required, name="dispatch")
class MigrateInPage(IdentityViewMixin, FormView):
    """
    Lets the identity's profile be migrated in or out.
    """

    template_name = "settings/migrate_in.html"
    extra_context = {"section": "migrate_in"}

    class form_class(forms.Form):
        alias = forms.CharField(
            help_text="The @account@example.com username you want to move here"
        )

        def clean_alias(self):
            self.alias_identity = Identity.by_handle(
                self.cleaned_data["alias"], fetch=True
            )
            if self.alias_identity is None:
                raise forms.ValidationError("Cannot find that account.")
            return self.alias_identity.actor_uri

    def form_valid(self, form):
        self.identity.add_alias(form.cleaned_data["alias"])
        messages.info(self.request, f"Alias to {form.alias_identity.handle} added")
        return redirect(".")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # If they asked for an alias deletion, do it here
        if "remove_alias" in self.request.GET:
            self.identity.remove_alias(self.request.GET["remove_alias"])
        context["aliases"] = []
        if self.identity.aliases:
            context["aliases"] = [
                Identity.by_actor_uri(uri) for uri in self.identity.aliases
            ]
        return context
