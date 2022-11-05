from django.conf import settings
from django.shortcuts import get_object_or_404

from users.models import Identity


def by_handle_or_404(request, handle, local=True):
    """
    Retrieves an Identity by its long or short handle.
    Domain-sensitive, so it will understand short handles on alternate domains.
    """
    # TODO: Domain sensitivity
    if "@" not in handle:
        handle += "@" + settings.DEFAULT_DOMAIN
    if local:
        return get_object_or_404(Identity.objects.filter(local=True), handle=handle)
    else:
        return get_object_or_404(Identity, handle=handle)
