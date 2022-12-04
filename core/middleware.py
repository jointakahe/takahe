from django.core.exceptions import MiddlewareNotUsed

from core import sentry
from core.models import Config


class ConfigLoadingMiddleware:
    """
    Caches the system config every request
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        Config.system = Config.load_system()
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
