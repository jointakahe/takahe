from collections.abc import Callable
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
            return JsonResponse({"error": "identity_token_required"}, status=401)
        return function(request, *args, **kwargs)

    # This is for the API only
    inner.csrf_exempt = True

    return inner


def scope_required(scope: str, requires_identity=True):
    """
    Asserts that the token we're using has the provided scope
    """

    def decorator(function: Callable):
        @wraps(function)
        def inner(request, *args, **kwargs):
            if not request.token:
                return JsonResponse({"error": "identity_token_required"}, status=401)
            # They need an identity
            if not request.identity and requires_identity:
                return JsonResponse({"error": "identity_token_required"}, status=401)
            if not request.token.has_scope(scope):
                return JsonResponse({"error": "out_of_scope_for_token"}, status=403)
            return function(request, *args, **kwargs)

        inner.csrf_exempt = True  # type:ignore
        return inner

    return decorator
