from users.models import Identity


class IdentityMiddleware:
    """
    Adds a request.identity object which is either the current session's
    identity, or None if they have not picked one yet/it's invalid.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        identity_id = request.session.get("identity_id")
        if not identity_id:
            request.identity = None
        else:
            try:
                request.identity = Identity.objects.get(id=identity_id)
            except Identity.DoesNotExist:
                request.identity = None

        response = self.get_response(request)
        return response
