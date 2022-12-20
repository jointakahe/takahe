from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect


def identity_required(function):
    """
    Decorator for views that ensures an active identity is selected.
    """

    @wraps(function)
    def inner(request, *args, **kwargs):
        # They do have to be logged in
        if not request.user.is_authenticated:
            return redirect_to_login(next=request.get_full_path())
        # If there's no active one, try to auto-select one
        if request.identity is None:
            possible_identities = list(request.user.identities.all())
            if len(possible_identities) != 1:
                # OK, send them to the identity selection page to select/create one
                return HttpResponseRedirect("/identity/select/")
            identity = possible_identities[0]
            request.session["identity_id"] = identity.pk
            request.identity = identity
        return function(request, *args, **kwargs)

    return inner


def moderator_required(function):
    return user_passes_test(
        lambda user: user.is_authenticated and (user.admin or user.moderator)
    )(function)


def admin_required(function):
    return user_passes_test(lambda user: user.is_authenticated and user.admin)(function)
