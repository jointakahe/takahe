from core.models import Config


class AlwaysSecureMiddleware:
    """
    Locks the request object as always being secure, for when it's behind
    a HTTPS reverse proxy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.__class__.scheme = "https"
        response = self.get_response(request)
        return response


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
