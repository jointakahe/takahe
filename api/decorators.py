from functools import wraps

from django.http import JsonResponse

from api.models import has_required_scopes


def scope_required(scope: str | None):
    """
    API version of the identity_required decorator that just makes sure the
    token is tied to an identity, not an app only.
    """
    required_scopes = set(scope.split()) if scope else set()

    def deco(function):
        @wraps(function)
        def inner(request, *args, **kwargs):
            # They need an identity
            if not request.identity:
                return JsonResponse({"error": "identity_token_required"}, status=401)
            if not has_required_scopes(
                request.token_scopes or "read", required=required_scopes
            ):
                raise JsonResponse({"error": "invalid_token_scope"}, status=401)
            return function(request, *args, **kwargs)

        return inner

    return deco


identity_required = scope_required(scope=None)
