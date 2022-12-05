from functools import partial, wraps

from django.views.decorators.cache import cache_page as dj_cache_page

from core.models import Config


def cache_page(
    timeout: int | str = "cache_timeout_page_default",
    *,
    per_identity: bool = False,
    key_prefix: str = "",
):
    """
    Decorator for views that caches the page result.
    timeout can either be the number of seconds or the name of a SystemOptions
    value.
    """
    if isinstance(timeout, str):
        timeout = Config.lazy_system_value(timeout)

    def decorator(function):
        @wraps(function)
        def inner(request, *args, **kwargs):
            prefix = key_prefix
            if per_identity:
                identity_id = request.identity.pk if request.identity else "0"
                prefix = f"{key_prefix or ''}:ident{identity_id}"
            _timeout = timeout
            if callable(_timeout):
                _timeout = _timeout()
            return dj_cache_page(timeout=_timeout, key_prefix=prefix)(function)(
                request, *args, **kwargs
            )

        return inner

    return decorator


per_identity_cache_page = partial(cache_page, per_identity=True)
