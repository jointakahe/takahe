import base64
import secrets
from urllib.parse import urlparse, urlunparse

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from api.models import Application, Authorization, Token
from api.parser import FormOrJsonParser


class OauthRedirect(HttpResponseRedirect):
    def __init__(self, redirect_uri, **kwargs):
        url_parts = urlparse(redirect_uri)
        self.allowed_schemes = [url_parts.scheme]
        # Either add or join the query section
        url_parts = list(url_parts)

        query_string = url_parts[4]

        for key, value in kwargs.items():
            if value is None:
                continue
            if not query_string:
                query_string = f"{key}={value}"
            else:
                query_string += f"&{key}={value}"

        url_parts[4] = query_string
        super().__init__(urlunparse(url_parts))


class AuthorizationView(LoginRequiredMixin, View):
    """
    Asks the user to authorize access.

    Could maybe be a FormView, but things are weird enough we just handle the
    POST manually.
    """

    def get(self, request):
        redirect_uri = self.request.GET["redirect_uri"]
        scope = self.request.GET.get("scope", "read")
        state = self.request.GET.get("state")

        response_type = self.request.GET.get("response_type")
        if response_type != "code":
            return render(
                request,
                "api/oauth_error.html",
                {"error": f"Invalid response type '{response_type}'"},
            )

        application = Application.objects.filter(
            client_id=self.request.GET.get("client_id"),
        ).first()

        if application is None:
            return render(
                request, "api/oauth_error.html", {"error": "Invalid client_id"}
            )

        if application.redirect_uris and redirect_uri not in application.redirect_uris:
            return render(
                request,
                "api/oauth_error.html",
                {"error": "Invalid application redirect URI"},
            )

        context = {
            "application": application,
            "state": state,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "identities": self.request.user.identities.all(),
        }
        return render(request, "api/oauth_authorize.html", context)

    def post(self, request):
        post_data = FormOrJsonParser().parse_body(request)
        # Grab the application and other details again
        redirect_uri = post_data["redirect_uri"]
        scope = post_data["scope"]
        application = Application.objects.get(client_id=post_data["client_id"])
        # Get the identity
        identity = self.request.user.identities.get(pk=post_data["identity"])

        extra_args = {}
        if post_data.get("state"):
            extra_args["state"] = post_data["state"]

        # Make a token
        token = Authorization.objects.create(
            application=application,
            user=self.request.user,
            identity=identity,
            code=secrets.token_urlsafe(43),
            redirect_uri=redirect_uri,
            scopes=scope.split(),
        )
        # If it's an out of band request, show the code
        if redirect_uri == "urn:ietf:wg:oauth:2.0:oob":
            return render(request, "api/oauth_code.html", {"code": token.code})
        # Redirect with the token's code
        return OauthRedirect(redirect_uri, code=token.code, **extra_args)


def extract_client_info_from_basic_auth(request):
    if "authorization" in request.headers:
        auth = request.headers["authorization"].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                client_id, client_secret = (
                    base64.b64decode(auth[1]).decode("utf8").split(":", 1)
                )

                return client_id, client_secret
    return None, None


@method_decorator(csrf_exempt, name="dispatch")
class TokenView(View):
    def verify_code(
        self, authorization: Authorization, client_id, client_secret, redirect_uri
    ):
        application = authorization.application
        return (
            application.client_id == client_id
            and application.client_secret == client_secret
            and authorization.redirect_uri == redirect_uri
        )

    def post(self, request):
        post_data = FormOrJsonParser().parse_body(request)
        auth_client_id, auth_client_secret = extract_client_info_from_basic_auth(
            request
        )
        post_data.setdefault("client_id", auth_client_id)
        post_data.setdefault("client_secret", auth_client_secret)

        grant_type = post_data.get("grant_type")
        if grant_type not in (
            "authorization_code",
            "client_credentials",
        ):
            return JsonResponse({"error": "invalid_grant_type"}, status=400)

        if grant_type == "client_credentials":
            # TODO: Implement client credentials flow
            return JsonResponse(
                {
                    "error": "invalid_grant_type",
                    "error_description": "client credential flow not implemented",
                },
                status=400,
            )
        elif grant_type == "authorization_code":
            code = post_data.get("code")
            if not code:
                return JsonResponse(
                    {
                        "error": "invalid_request",
                        "error_description": "Required param : code",
                    },
                    status=400,
                )

            authorization = Authorization.objects.get(code=code)
            if (
                not authorization
                or timezone.now() - authorization.created
                > timezone.timedelta(seconds=authorization.valid_for_seconds)
            ):
                return JsonResponse({"error": "access_denied"}, status=401)

            application = Application.objects.filter(
                client_id=post_data["client_id"],
                client_secret=post_data["client_secret"],
            ).first()

            code_verified = self.verify_code(
                authorization,
                client_id=post_data.get("client_id"),
                client_secret=post_data.get("client_secret"),
                redirect_uri=post_data.get("redirect_uri"),
            )

            if not application or authorization.token or not code_verified:
                # this authorization code has already been used
                return JsonResponse({"error": "access_denied"}, status=401)

            token = Token.objects.create(
                application=application,
                user=authorization.user,
                identity=authorization.identity,
                token=secrets.token_urlsafe(43),
                scopes=authorization.scopes,
            )
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


@method_decorator(csrf_exempt, name="dispatch")
class RevokeTokenView(View):
    def post(self, request):
        post_data = FormOrJsonParser().parse_body(request)
        auth_client_id, auth_client_secret = extract_client_info_from_basic_auth(
            request
        )
        post_data.setdefault("client_id", auth_client_id)
        post_data.setdefault("client_secret", auth_client_secret)
        token_str = post_data["token"]

        application = Application.objects.filter(
            client_id=post_data["client_id"],
            client_secret=post_data["client_secret"],
        ).first()

        token = Token.objects.filter(application=application, token=token_str).first()
        if token is None:
            return HttpResponseForbidden()

        token.revoked = timezone.now()
        token.save()
        return HttpResponse("")
