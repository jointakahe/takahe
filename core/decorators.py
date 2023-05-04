from collections.abc import Callable
from functools import partial, wraps
from typing import ParamSpecArgs, ParamSpecKwargs

from django.http import HttpRequest
from django.views.decorators.cache import cache_page as dj_cache_page

from core.models import Config

VaryByFunc = Callable[[HttpRequest, ParamSpecArgs, ParamSpecKwargs], str]


def vary_by_ap_json(request, *args, **kwargs) -> str:
    """
    Return a cache usable string token that is different based upon Accept
    header.
    """
    if request.ap_json:
        return "ap_json"
    return "not_ap"


def cache_page(
    timeout: int | str = "cache_timeout_page_default",
    *,
    key_prefix: str = "",
    public_only: bool = False,
    vary_by: VaryByFunc | list[VaryByFunc] | None = None,
):
    """
    Decorator for views that caches the page result.
    timeout can either be the number of seconds or the name of a SystemOptions
    value.
    If public_only is True, requests with an identity are not cached.
    """
    _timeout = timeout
    _prefix = key_prefix
    if callable(vary_by):
        vary_by = [vary_by]

    def decorator(function):
        @wraps(function)
        def inner(request, *args, **kwargs):
            if public_only:
                if request.user.is_authenticated:
                    return function(request, *args, **kwargs)

            prefix = [_prefix]

            if isinstance(vary_by, list):
                prefix.extend([vfunc(request, *args, **kwargs) for vfunc in vary_by])

            prefix = "".join(prefix)

            if isinstance(_timeout, str):
                timeout = getattr(Config.system, _timeout)
            else:
                timeout = _timeout

            return dj_cache_page(timeout=timeout, key_prefix=prefix)(function)(
                request, *args, **kwargs
            )

        return inner

    return decorator


cache_page_by_ap_json = partial(cache_page, vary_by=[vary_by_ap_json])
