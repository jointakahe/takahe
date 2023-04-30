from users.models import Domain


class DomainMiddleware:
    """
    Tries to attach a Domain object to every incoming request, if one matches.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.domain = None
        if "HTTP_HOST" in request.META:
            request.domain = Domain.get_domain(request.META["HTTP_HOST"])
        response = self.get_response(request)
        return response
