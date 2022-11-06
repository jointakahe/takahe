import base64
import uuid
from functools import partial
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
import urlman
from asgiref.sync import sync_to_async
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.db import models
from django.utils import timezone
from django.utils.http import http_date
from OpenSSL import crypto

from core.ld import canonicalise
from users.models.domain import Domain


def upload_namer(prefix, instance, filename):
    """
    Names uploaded images etc.
    """
    now = timezone.now()
    filename = base64.b32encode(uuid.uuid4().bytes).decode("ascii")
    return f"{prefix}/{now.year}/{now.month}/{now.day}/{filename}"


class Identity(models.Model):
    """
    Represents both local and remote Fediverse identities (actors)
    """

    # The Actor URI is essentially also a PK - we keep the default numeric
    # one around as well for making nice URLs etc.
    actor_uri = models.CharField(max_length=500, blank=True, null=True, unique=True)

    local = models.BooleanField()
    users = models.ManyToManyField("users.User", related_name="identities")

    username = models.CharField(max_length=500, blank=True, null=True)
    # Must be a display domain if present
    domain = models.ForeignKey(
        "users.Domain",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )

    name = models.CharField(max_length=500, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    manually_approves_followers = models.BooleanField(blank=True, null=True)

    profile_uri = models.CharField(max_length=500, blank=True, null=True)
    inbox_uri = models.CharField(max_length=500, blank=True, null=True)
    outbox_uri = models.CharField(max_length=500, blank=True, null=True)
    icon_uri = models.CharField(max_length=500, blank=True, null=True)
    image_uri = models.CharField(max_length=500, blank=True, null=True)

    icon = models.ImageField(
        upload_to=partial(upload_namer, "profile_images"), blank=True, null=True
    )
    image = models.ImageField(
        upload_to=partial(upload_namer, "background_images"), blank=True, null=True
    )

    private_key = models.TextField(null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    fetched = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "identities"
        unique_together = [("username", "domain")]

    @classmethod
    def by_handle(cls, handle, fetch=False, local=False):
        if handle.startswith("@"):
            raise ValueError("Handle must not start with @")
        if "@" not in handle:
            raise ValueError("Handle must contain domain")
        username, domain = handle.split("@")
        try:
            if local:
                return cls.objects.get(username=username, domain_id=domain, local=True)
            else:
                return cls.objects.get(username=username, domain_id=domain)
        except cls.DoesNotExist:
            if fetch and not local:
                return cls.objects.create(handle=handle, local=False)
            return None

    @classmethod
    def by_actor_uri(cls, uri) -> Optional["Identity"]:
        try:
            return cls.objects.get(actor_uri=uri)
        except cls.DoesNotExist:
            return None

    @classmethod
    def by_actor_uri_with_create(cls, uri) -> "Identity":
        try:
            return cls.objects.get(actor_uri=uri)
        except cls.DoesNotExist:
            return cls.objects.create(actor_uri=uri, local=False)

    @property
    def handle(self):
        return f"{self.username}@{self.domain_id}"

    @property
    def data_age(self) -> float:
        """
        How old our copy of this data is, in seconds
        """
        if self.local:
            return 0
        if self.fetched is None:
            return 10000000000
        return (timezone.now() - self.fetched).total_seconds()

    def generate_keypair(self):
        if not self.local:
            raise ValueError("Cannot generate keypair for remote user")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.private_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.save()

    @classmethod
    async def fetch_webfinger(cls, handle: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Given a username@domain handle, returns a tuple of
        (actor uri, canonical handle) or None, None if it does not resolve.
        """
        domain = handle.split("@")[1]
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{domain}/.well-known/webfinger?resource=acct:{handle}",
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
        if response.status_code >= 400:
            return None, None
        data = response.json()
        if data["subject"].startswith("acct:"):
            data["subject"] = data["subject"][5:]
        for link in data["links"]:
            if (
                link.get("type") == "application/activity+json"
                and link.get("rel") == "self"
            ):
                return link["href"], data["subject"]
        return None, None

    async def fetch_actor(self) -> bool:
        """
        Fetches the user's actor information, as well as their domain from
        webfinger if it's available.
        """
        if self.local:
            raise ValueError("Cannot fetch local identities")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.actor_uri,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
            if response.status_code >= 400:
                return False
            document = canonicalise(response.json(), include_security=True)
            self.name = document.get("name")
            self.profile_uri = document.get("url")
            self.inbox_uri = document.get("inbox")
            self.outbox_uri = document.get("outbox")
            self.summary = document.get("summary")
            self.username = document.get("preferredUsername")
            self.manually_approves_followers = document.get(
                "as:manuallyApprovesFollowers"
            )
            self.public_key = document.get("publicKey", {}).get("publicKeyPem")
            self.icon_uri = document.get("icon", {}).get("url")
            self.image_uri = document.get("image", {}).get("url")
        # Now go do webfinger with that info to see if we can get a canonical domain
        actor_url_parts = urlparse(self.actor_uri)
        get_domain = sync_to_async(Domain.get_remote_domain)
        if self.username:
            webfinger_actor, webfinger_handle = await self.fetch_webfinger(
                f"{self.username}@{actor_url_parts.hostname}"
            )
            if webfinger_handle:
                webfinger_username, webfinger_domain = webfinger_handle.split("@")
                self.username = webfinger_username
                self.domain = await get_domain(webfinger_domain)
            else:
                self.domain = await get_domain(actor_url_parts.hostname)
        else:
            self.domain = await get_domain(actor_url_parts.hostname)
        self.fetched = timezone.now()
        await sync_to_async(self.save)()
        return True

    def sign(self, cleartext: str) -> str:
        if not self.private_key:
            raise ValueError("Cannot sign - no private key")
        private_key = serialization.load_pem_private_key(
            self.private_key.encode("ascii"),
            password=None,
        )
        return base64.b64encode(
            private_key.sign(
                cleartext.encode("ascii"),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        ).decode("ascii")

    def verify_signature(self, signature: bytes, cleartext: str) -> bool:
        if not self.public_key:
            raise ValueError("Cannot verify - no public key")
        x509 = crypto.X509()
        x509.set_pubkey(
            crypto.load_publickey(
                crypto.FILETYPE_PEM,
                self.public_key.encode("ascii"),
            )
        )
        try:
            crypto.verify(x509, signature, cleartext.encode("ascii"), "sha256")
        except crypto.Error:
            return False
        return True

    async def signed_request(self, host, method, path, document):
        """
        Delivers the document to the specified host, method, path and signed
        as this user.
        """
        date_string = http_date(timezone.now().timestamp())
        headers = {
            "(request-target)": f"{method} {path}",
            "Host": host,
            "Date": date_string,
        }
        headers_string = " ".join(headers.keys())
        signed_string = "\n".join(f"{name}: {value}" for name, value in headers.items())
        signature = self.sign(signed_string)
        del headers["(request-target)"]
        headers[
            "Signature"
        ] = f'keyId="{self.urls.key.full()}",headers="{headers_string}",signature="{signature}"'
        async with httpx.AsyncClient() as client:
            return await client.request(
                method,
                "https://{host}{path}",
                headers=headers,
                data=document,
            )

    def validate_signature(self, request):
        """
        Attempts to validate the signature on an incoming request.
        Returns False if the signature is invalid, None if it cannot be verified
        as we do not have the key locally, or the name of the actor if it is valid.
        """
        pass

    def __str__(self):
        return self.handle or self.actor_uri

    class urls(urlman.Urls):
        view = "/@{self.username}@{self.domain_id}/"
        view_short = "/@{self.username}/"
        actor = "{view}actor/"
        key = "{actor}#main-key"
        inbox = "{actor}inbox/"
        outbox = "{actor}outbox/"
        activate = "{view}activate/"

        def get_scheme(self, url):
            return "https"

        def get_hostname(self, url):
            return self.instance.domain.uri_domain
