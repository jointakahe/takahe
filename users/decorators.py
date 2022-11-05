from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect

from users.models import Identity


def identity_required(function):
    """
    Decorator for views that ensures an active identity is selected.
    """

    @wraps(function)
    def inner(request, *args, **kwargs):
        # They do have to be logged in
        if not request.user.is_authenticated:
            return redirect_to_login(next=request.get_full_path())
        # Try to retrieve their active identity
        identity_id = request.session.get("identity_id")
        if not identity_id:
            identity = None
        else:
            try:
                identity = Identity.objects.get(id=identity_id)
            except Identity.DoesNotExist:
                identity = None
        # If there's no active one, try to auto-select one
        if identity is None:
            possible_identities = list(request.user.identities.all())
            if len(possible_identities) != 1:
                # OK, send them to the identity selection page to select/create one
                return HttpResponseRedirect("/identity/select/")
            identity = possible_identities[0]
        request.identity = identity
        request.session["identity_id"] = identity.pk
        return function(request, *args, **kwargs)

    return inner
