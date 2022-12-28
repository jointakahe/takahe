from django.http import Http404

from users.models import Domain, Identity


def by_handle_or_404(request, handle, local=True, fetch=False) -> Identity:
    """
    Retrieves an Identity by its long or short handle.
    Domain-sensitive, so it will understand short handles on alternate domains.
    """
    if "@" not in handle:
        if "host" not in request.headers:
            raise Http404("No hostname available")
        username = handle
        domain_instance = Domain.get_domain(request.headers["host"])
        if domain_instance is None:
            raise Http404("No matching domains found")
        domain = domain_instance.domain
    else:
        username, domain = handle.split("@", 1)
        # Resolve the domain to the display domain
        domain_instance = Domain.get_domain(domain)
        if domain_instance is None:
            domain_instance = Domain.get_remote_domain(domain)
        domain = domain_instance.domain
    identity = Identity.by_username_and_domain(
        username,
        domain_instance,
        local=local,
        fetch=fetch,
    )
    if identity is None:
        raise Http404(f"No identity for handle {handle}")
    if identity.blocked:
        raise Http404("Blocked user")
    return identity
