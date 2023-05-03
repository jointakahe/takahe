from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import FormView

from users.views.base import IdentityViewMixin


class DeleteIdentity(IdentityViewMixin, FormView):

    template_name = "settings/delete.html"
    extra_context = {"section": "delete"}

    class form_class(forms.Form):
        confirmation = forms.CharField(
            help_text="Write the word DELETE in this box if you wish to delete this account",
            required=True,
        )

        def clean_confirmation(self):
            value = self.cleaned_data.get("confirmation")
            if value.lower() != "delete":
                raise forms.ValidationError("You must write DELETE here")
            return value

    def form_valid(self, form):
        self.identity.mark_deleted()
        messages.success(
            self.request,
            f"The identity {self.identity.handle} is now being deleted.",
        )
        return redirect("/")
