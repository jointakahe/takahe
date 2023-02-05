from functools import wraps

from django.http import JsonResponse


def identity_required(function):
    """
    API version of the identity_required decorator that just makes sure the
    token is tied to one, not an app only.
    """

    @wraps(function)
    def inner(request, *args, **kwargs):
        # They need an identity
        if not request.identity:
            return JsonResponse({"error": "identity_token_required"}, status=400)
        return function(request, *args, **kwargs)

    # This is for the API only
    inner.csrf_exempt = True

    return inner
