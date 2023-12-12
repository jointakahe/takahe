"""
Wrapper around HTTPX that provides some fedi-specific features.

The API is identical to httpx, but some features has been added:

* Fedi-compatible HTTP signatures
* Blocked IP ranges

(Because Y is next after X).
"""
import ipaddress
import typing
from types import EllipsisType

import httpx
from django.conf import settings


class SigningActor(typing.Protocol):
    #: The private key used for signing, in PEM format
    private_key: str

    # This is pretty much part of the interface, but we don't need it when
    # making requests.
    # public_key: str

    #: The URL we should use to advertise this key
    public_key_id: str


class Client(httpx.Client):
    def __init__(
        self,
        *,
        actor: SigningActor | None = None,
        blocked_ranges: list[ipaddress.IPv4Network | ipaddress.IPv6Network | str]
        | None
        | EllipsisType = ...,
        **opts
    ):
        """
        Params:
          actor: Actor to sign requests as, or None to not sign requests.
          blocked_ranges: IP address to refuse to connect to. Either a list of
                         Networks, None to disable the feature, or Ellipsis to
                         pull the Django setting.
        """
        super().__init__(**opts)

        if blocked_ranges is ...:
            blocked_ranges = settings.HTTP_BLOCKED_RANGES

        if blocked_ranges is not None:
            # TODO: Do we want to cache this?
            blocked_ranges = [
                ipaddress.ip_network(net) if isinstance(net, str) else net
                for net in typing.cast(typing.Iterable, blocked_ranges)
            ]

        # TODO: If we're given blocked ranges, customize transport

        self.actor = actor
