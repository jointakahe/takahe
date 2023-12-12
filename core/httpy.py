"""
Wrapper around HTTPX that provides some fedi-specific features.

The API is identical to httpx, but some features has been added:

* Fedi-compatible HTTP signatures
* Blocked IP ranges

(Because Y is next after X).
"""
import functools
import ipaddress
import typing
from types import EllipsisType

import httpx
from django.conf import settings
from httpx._types import TimeoutTypes

from .signatures import HttpSignature


class SigningActor(typing.Protocol):
    """
    An AP Actor with keys, that can sign requests.

    Both :class:`users.models.identity.Identity`, and
    :class:`users.models.system_actor.SystemActor` implement this protocol.
    """

    #: The private key used for signing, in PEM format
    private_key: str

    # This is pretty much part of the interface, but we don't need it when
    # making requests.
    # public_key: str

    #: The URL we should use to advertise this key
    public_key_id: str


class SignedAuth(httpx.Auth):
    """
    Handles signing the request.
    """

    # Doing it this way so we get automatic sync/async handling
    requires_request_body = True

    def __init__(self, actor: SigningActor):
        self.actor = actor

    def auth_flow(self, request: httpx.Request):
        HttpSignature.sign_request(
            request, self.actor.private_key, self.actor.public_key_id
        )
        yield request


@functools.lru_cache  # Reuse transports
def _get_transport(
    blocked_ranges: list[ipaddress.IPv4Network | ipaddress.IPv6Network | str]
    | EllipsisType,
    sync: bool,
):
    """
    Gets an (Async)Transport that blocks the given IP ranges
    """
    if blocked_ranges is ...:
        blocked_ranges = settings.HTTP_BLOCKED_RANGES

    blocked_ranges = [
        ipaddress.ip_network(net) if isinstance(net, str) else net
        for net in typing.cast(typing.Iterable, blocked_ranges)
    ]


class BaseClient(httpx.BaseClient):
    def __init__(
        self,
        *,
        actor: SigningActor | None = None,
        blocked_ranges: list[ipaddress.IPv4Network | ipaddress.IPv6Network | str]
        | None
        | EllipsisType = ...,
        timeout: TimeoutTypes = settings.SETUP.REMOTE_TIMEOUT,
        **opts
    ):
        """
        Params:
          actor: Actor to sign requests as, or None to not sign requests.
          blocked_ranges: IP address to refuse to connect to. Either a list of
                         Networks, None to disable the feature, or Ellipsis to
                         pull the Django setting.
        """
        if actor:
            opts["auth"] = SignedAuth(actor)

        super().__init__(timeout=timeout, **opts)

        # TODO: If we're given blocked ranges, customize transport

    def build_request(self, *pargs, **kwargs):
        request = super().build_request(*pargs, **kwargs)

        # GET requests get implicit accept headers added
        if request.method == "GET" and "Accept" not in request.headers:
            request.headers["Accept"] = "application/ld+json"

        request.headers[
            "User-Agent"
        ] = settings.TAKAHE_USER_AGENT  # TODO: Move this to __init__
        return request


# BaseClient before (Async)Client because __init__


class Client(BaseClient, httpx.Client):
    pass


class AsyncClient(BaseClient, httpx.AsyncClient):
    pass
