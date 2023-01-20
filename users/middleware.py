from django.utils import timezone

from users.models import Identity, User


class IdentityMiddleware:
    """
    Adds a request.identity object which is either the current session's
    identity, or None if they have not picked one yet/it's invalid.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # The API middleware might have set identity already
        if not hasattr(request, "identity"):
            # See if we have one in the session
            identity_id = request.session.get("identity_id")
            if not identity_id:
                request.identity = None
            else:
                # Pull it out of the DB and assign it
                try:
                    request.identity = Identity.objects.get(id=identity_id)
                    User.objects.filter(pk=request.user.pk).update(
                        last_seen=timezone.now()
                    )
                except Identity.DoesNotExist:
                    request.identity = None

        response = self.get_response(request)

        if request.user:
            response.headers["X-Takahe-User"] = str(request.user)
        if request.identity:
            response.headers["X-Takahe-Identity"] = str(request.identity)

        return response
