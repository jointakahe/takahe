from urllib.parse import urljoin

from django.conf import settings


class RelativeAbsoluteUrl:
    """
    Represents a URL that can have both "relative" and "absolute" forms
    for various use either locally or remotely.
    """

    absolute: str
    relative: str

    def __init__(self, absolute: str, relative: str | None = None):
        if "://" not in absolute:
            raise ValueError(f"Absolute URL {absolute!r} is not absolute!")
        self.absolute = absolute
        self.relative = relative or absolute


class AutoAbsoluteUrl(RelativeAbsoluteUrl):
    """
    Automatically makes the absolute variant by using either settings.MAIN_DOMAIN
    or a passed identity's URI domain.
    """

    def __init__(self, relative: str, identity=None):
        self.relative = relative
        if identity:
            absolute_prefix = f"https://{identity.domain.uri_domain}/"
        else:
            absolute_prefix = f"https://{settings.MAIN_DOMAIN}/"
        self.absolute = urljoin(absolute_prefix, self.relative)
