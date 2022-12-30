import hashlib
import sys
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage


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

    def __init__(
        self,
        relative: str,
        identity=None,
    ):
        self.relative = relative
        if identity:
            absolute_prefix = f"https://{identity.domain.uri_domain}/"
        else:
            absolute_prefix = f"https://{settings.MAIN_DOMAIN}/"
        self.absolute = urljoin(absolute_prefix, self.relative)


class ProxyAbsoluteUrl(AutoAbsoluteUrl):
    """
    AutoAbsoluteUrl variant for proxy paths, that also attaches a remote URI hash
    plus extension to the end if it can.
    """

    def __init__(
        self,
        relative: str,
        identity=None,
        remote_url: str | None = None,
    ):
        if remote_url:
            # See if there is a file extension we can grab
            extension = "bin"
            remote_filename = remote_url.split("/")[-1]
            if "." in remote_filename:
                extension = remote_filename.split(".")[-1]
            # When provided, attach a hash of the remote URL
            # SHA1 chosen as it generally has the best performance in modern python, and security is not a concern
            # Hash truncation is generally fine, as in the typical use case the hash is scoped to the identity PK.
            relative += f"{hashlib.sha1(remote_url.encode('ascii')).hexdigest()[:10]}.{extension}"
        super().__init__(relative, identity)


class StaticAbsoluteUrl(RelativeAbsoluteUrl):
    """
    Creates static URLs given only the static-relative path
    """

    def __init__(self, path: str):
        try:
            static_url = staticfiles_storage.url(path)
        except ValueError:
            # Suppress static issues during the first collectstatic
            # Yes, I know it's a big hack! Pull requests welcome :)
            if "collectstatic" in sys.argv:
                super().__init__("https://example.com/")
                return
            raise
        if "://" in static_url:
            super().__init__(static_url)
        else:
            super().__init__(
                urljoin(f"https://{settings.MAIN_DOMAIN}/", static_url), static_url
            )
