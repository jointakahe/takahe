import secrets
from urllib.parse import urlparse

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from api.models import Application, Token


class OauthRedirect(HttpResponseRedirect):
    def __init__(self, redirect_uri, key, value):
        self.allowed_schemes = [urlparse(redirect_uri).scheme]
        super().__init__(redirect_uri + f"?{key}={value}")


class AuthorizationView(LoginRequiredMixin, TemplateView):
    """
    Asks the user to authorize access.

    Could maybe be a FormView, but things are weird enough we just handle the
    POST manually.
    """

    template_name = "api/oauth_authorize.html"

    def get_context_data(self):
        redirect_uri = self.request.GET["redirect_uri"]
        scope = self.request.GET.get("scope", "read")
        try:
            application = Application.objects.get(
                client_id=self.request.GET["client_id"]
            )
        except (Application.DoesNotExist, KeyError):
            return OauthRedirect(redirect_uri, "error", "invalid_application")
        return {
            "application": application,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "identities": self.request.user.identities.all(),
        }

    def post(self, request):
        # Grab the application and other details again
        redirect_uri = self.request.POST["redirect_uri"]
        scope = self.request.POST["scope"]
        application = Application.objects.get(client_id=self.request.POST["client_id"])
        # Get the identity
        identity = self.request.user.identities.get(pk=self.request.POST["identity"])
        # Make a token
        token = Token.objects.create(
            application=application,
            user=self.request.user,
            identity=identity,
            token=secrets.token_urlsafe(32),
            code=secrets.token_urlsafe(16),
            scopes=scope.split(),
        )
        # Redirect with the token's code
        return OauthRedirect(redirect_uri, "code", token.code)


@method_decorator(csrf_exempt, name="dispatch")
class TokenView(View):
    def post(self, request):
        grant_type = request.POST["grant_type"]
        try:
            application = Application.objects.get(
                client_id=self.request.POST["client_id"]
            )
        except (Application.DoesNotExist, KeyError):
            return JsonResponse({"error": "invalid_client_id"}, status=400)
        # TODO: Implement client credentials flow
        if grant_type == "client_credentials":
            return JsonResponse({"error": "invalid_grant_type"}, status=400)
        elif grant_type == "authorization_code":
            code = request.POST["code"]
            # Retrieve the token by code
            # TODO: Check code expiry based on created date
            try:
                token = Token.objects.get(code=code, application=application)
            except Token.DoesNotExist:
                return JsonResponse({"error": "invalid_code"}, status=400)
            # Update the token to remove its code
            token.code = None
            token.save()
            # Return them the token
            return JsonResponse(
                {
                    "access_token": token.token,
                    "token_type": "Bearer",
                    "scope": " ".join(token.scopes),
                    "created_at": int(token.created.timestamp()),
                }
            )


class RevokeTokenView(View):
    pass
