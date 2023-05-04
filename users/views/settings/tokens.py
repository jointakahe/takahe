import secrets

from django import forms
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView
from django.views.generic.list import ListView

from api.models.application import Application
from api.models.token import Token
from users.views.base import IdentityViewMixin


class TokensRoot(IdentityViewMixin, ListView):
    """
    Shows a listing of tokens the user has authorized
    """

    template_name = "settings/tokens.html"
    extra_context = {"section": "tokens"}
    context_object_name = "tokens"

    def get_queryset(self):
        return Token.objects.filter(
            user=self.request.user,
            identity=self.identity,
        ).prefetch_related("application")


class TokenCreate(IdentityViewMixin, FormView):
    """
    Allows the user to create a new app and token just for themselves.
    """

    template_name = "settings/token_create.html"
    extra_context = {"section": "tokens"}

    class form_class(forms.Form):
        name = forms.CharField(help_text="Identifies this app in your app list")
        scope = forms.ChoiceField(
            choices=(("read", "Read-only access"), ("write", "Full access")),
            help_text="What should this app be able to do with your account?",
        )

    def form_valid(self, form):
        scopes = "read write push" if form.cleaned_data["scope"] == "write" else "read"
        application = Application.create(
            client_name=form.cleaned_data["name"],
            website=None,
            redirect_uris="urn:ietf:wg:oauth:2.0:oob",
            scopes=scopes,
        )
        token = Token.objects.create(
            application=application,
            user=self.request.user,
            identity=self.identity,
            token=secrets.token_urlsafe(43),
            scopes=scopes,
        )
        return redirect("settings_token_edit", handle=self.identity.handle, pk=token.pk)


class TokenEdit(IdentityViewMixin, DetailView):

    template_name = "settings/token_edit.html"
    extra_context = {"section": "tokens"}

    def get_queryset(self):
        return self.identity.tokens

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        messages.success(
            request, f"{self.object.application.name}'s access has been removed."
        )
        self.object.delete()
        return redirect("settings_tokens", handle=self.identity.handle)
