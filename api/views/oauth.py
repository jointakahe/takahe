import secrets
from urllib.parse import urlparse, urlunparse

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from api.models import Application, Token
from api.parser import FormOrJsonParser


class OauthRedirect(HttpResponseRedirect):
    def __init__(self, redirect_uri, key, value):
        url_parts = urlparse(redirect_uri)
        self.allowed_schemes = [url_parts.scheme]
        # Either add or join the query section
        url_parts = list(url_parts)
        if url_parts[4]:
            url_parts[4] = url_parts[4] + f"&{key}={value}"
        else:
            url_parts[4] = f"{key}={value}"
        super().__init__(urlunparse(url_parts))


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
        post_data = FormOrJsonParser().parse_body(request)
        # Grab the application and other details again
        redirect_uri = post_data["redirect_uri"]
        scope = post_data["scope"]
        application = Application.objects.get(client_id=post_data["client_id"])
        # Get the identity
        identity = self.request.user.identities.get(pk=post_data["identity"])
        # Make a token
        token = Token.objects.create(
            application=application,
            user=self.request.user,
            identity=identity,
            token=secrets.token_urlsafe(32),
            code=secrets.token_urlsafe(16),
            scopes=scope.split(),
        )
        # If it's an out of band request, show the code
        if redirect_uri == "urn:ietf:wg:oauth:2.0:oob":
            return render(request, "api/oauth_code.html", {"code": token.code})
        # Redirect with the token's code
        return OauthRedirect(redirect_uri, "code", token.code)


@method_decorator(csrf_exempt, name="dispatch")
class TokenView(View):
    def post(self, request):
        post_data = FormOrJsonParser().parse_body(request)

        grant_type = post_data.get("grant_type")
        if grant_type not in (
            "authorization_code",
            "client_credentials",
        ):
            return JsonResponse({"error": "invalid_grant_type"}, status=400)

        try:
            application = Application.objects.get(client_id=post_data["client_id"])
        except (Application.DoesNotExist, KeyError):
            return JsonResponse({"error": "invalid_client_id"}, status=400)
        # TODO: Implement client credentials flow
        if grant_type == "client_credentials":
            return JsonResponse({"error": "invalid_grant_type"}, status=400)
        elif grant_type == "authorization_code":
            code = post_data.get("code")
            if not code:
                return JsonResponse({"error": "invalid_code"}, status=400)
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
