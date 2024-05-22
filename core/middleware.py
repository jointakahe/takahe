import json
from time import time

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

from core import sentry
from core.models import Config


class HeadersMiddleware:
    """
    Deals with Accept request headers, and Cache-Control response ones.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        accept = request.headers.get("accept", "text/html").lower()
        request.ap_json = (
            "application/json" in accept
            or "application/ld" in accept
            or "application/activity" in accept
        )
        response = self.get_response(request)
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


class ConfigLoadingMiddleware:
    """
    Caches the system config every request
    """

    refresh_interval: float = 5.0

    def __init__(self, get_response):
        self.get_response = get_response
        self.config_ts: float = 0.0

    def __call__(self, request):
        # Allow test fixtures to force and lock the config
        if not getattr(Config, "__forced__", False):
            if (
                not getattr(Config, "system", None)
                or (time() - self.config_ts) >= self.refresh_interval
            ):
                Config.system = Config.load_system()
                self.config_ts = time()
        response = self.get_response(request)
        return response


class SentryTaggingMiddleware:
    """
    Sets Sentry tags at the start of the request if Sentry is configured.
    """

    def __init__(self, get_response):
        if not sentry.SENTRY_ENABLED:
            raise MiddlewareNotUsed()
        self.get_response = get_response

    def __call__(self, request):
        sentry.set_takahe_app("web")
        response = self.get_response(request)
        return response


def show_toolbar(request):
    """
    Determines whether to show the debug toolbar on a given page.
    """
    return settings.DEBUG and request.user.is_authenticated and request.user.admin


class ParamsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def make_params(self, request):
        # See https://docs.joinmastodon.org/client/intro/#parameters
        # If they sent JSON, use that.
        if request.content_type == "application/json" and request.body.strip():
            return json.loads(request.body)
        # Otherwise, fall back to form data.
        params = {}
        for key, value in request.GET.items():
            params[key] = value
        for key, value in request.POST.items():
            params[key] = value
        return params

    def __call__(self, request):
        request.PARAMS = self.make_params(request)
        return self.get_response(request)
