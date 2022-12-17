from time import time

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
