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
