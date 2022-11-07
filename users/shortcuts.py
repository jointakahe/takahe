from django.http import Http404

from users.models import Domain, Identity


def by_handle_or_404(request, handle, local=True, fetch=False):
    """
    Retrieves an Identity by its long or short handle.
    Domain-sensitive, so it will understand short handles on alternate domains.
    """
    if "@" not in handle:
        if "HTTP_HOST" not in request.META:
            raise Http404("No hostname available")
        username = handle
        domain_instance = Domain.get_local_domain(request.META["HTTP_HOST"])
        if domain_instance is None:
            raise Http404("No matching domains found")
        domain = domain_instance.domain
    else:
        username, domain = handle.split("@", 1)
    identity = Identity.by_handle(handle, local=local, fetch=fetch)
    if identity is None:
        raise Http404(f"No identity for handle {handle}")
    return identity
