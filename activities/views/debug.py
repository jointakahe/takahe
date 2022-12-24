import pprint

import httpx
from asgiref.sync import async_to_sync
from django import forms
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from core.ld import canonicalise
from users.decorators import admin_required
from users.models import SystemActor


@method_decorator(admin_required, name="dispatch")
class JsonViewer(FormView):

    template_name = "activities/debug_json.html"

    class form_class(forms.Form):
        uri = forms.CharField(
            help_text="The URI to fetch and show",
            widget=forms.TextInput(attrs={"type": "search", "autofocus": "autofocus"}),
        )

    def form_valid(self, form):
        raw_result = ""
        uri = form.cleaned_data["uri"]
        if "://" not in uri:
            uri = "https://" + uri
        try:
            response = async_to_sync(SystemActor().signed_request)(
                method="get",
                uri=uri,
            )
        except httpx.RequestError:
            result = "Request Error"
        else:
            raw_result = response.text
            if response.status_code >= 400:
                result = f"Error response: {response.status_code}\n{response.content}"
            else:
                document = canonicalise(response.json(), include_security=True)
                result = pprint.pformat(document)
        # Render results
        context = self.get_context_data(form=form)
        context["result"] = result
        context["raw_result"] = raw_result
        return self.render_to_response(context)


class NotFound(TemplateView):

    template_name = "404.html"


class ServerError(TemplateView):

    template_name = "500.html"


@method_decorator(admin_required, name="dispatch")
class OauthAuthorize(TemplateView):

    template_name = "api/oauth_authorize.html"

    def get_context_data(self):
        return {
            "application": {"name": "Fake Application", "client_id": "fake"},
            "redirect_uri": "",
            "scope": "read write push",
            "identities": self.request.user.identities.all(),
            "code": "12345abcde",
        }
