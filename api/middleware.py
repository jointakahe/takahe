from django.http import HttpResponse

from api.models import Token


class ApiTokenMiddleware:
    """
    Adds request.user and request.identity if an API token appears.
    Also nukes request.session so it can't be used accidentally.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.headers.get("authorization", None)
        request.token = None
        request.identity = None
        if auth_header and auth_header.startswith("Bearer "):
            token_value = auth_header[7:]
            if token_value == "__app__":
                # Special client app token value
                pass
            else:
                try:
                    token = Token.objects.get(token=token_value, revoked=None)
                except Token.DoesNotExist:
                    return HttpResponse("Invalid Bearer token", status=400)
                request.user = token.user
                request.identity = token.identity
                request.token = token
            request.session = None
        response = self.get_response(request)
        return response
