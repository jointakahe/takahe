import base64
import uuid
from functools import partial

import httpx
import urlman
from asgiref.sync import sync_to_async
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.http import http_date

from core.ld import canonicalise


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

    # The handle includes the domain!
    handle = models.CharField(max_length=500, unique=True)
    name = models.CharField(max_length=500, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)

    actor_uri = models.CharField(max_length=500, blank=True, null=True, db_index=True)
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

    local = models.BooleanField()
    users = models.ManyToManyField("users.User", related_name="identities")
    manually_approves_followers = models.BooleanField(blank=True, null=True)
    private_key = models.TextField(null=True, blank=True)
    public_key = models.TextField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    fetched = models.DateTimeField(null=True, blank=True)
    deleted = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "identities"

    @classmethod
    def by_handle(cls, handle, create=True):
        if handle.startswith("@"):
            raise ValueError("Handle must not start with @")
        if "@" not in handle:
            raise ValueError("Handle must contain domain")
        try:
            return cls.objects.filter(handle=handle).get()
        except cls.DoesNotExist:
            if create:
                return cls.objects.create(handle=handle, local=False)
            return None

    @classmethod
    def by_actor_uri(cls, uri):
        try:
            cls.objects.filter(actor_uri=uri)
        except cls.DoesNotExist:
            return None

    @property
    def short_handle(self):
        if self.handle.endswith("@" + settings.DEFAULT_DOMAIN):
            return self.handle.split("@", 1)[0]
        return self.handle

    @property
    def domain(self):
        return self.handle.split("@", 1)[1]

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

    async def fetch_details(self):
        if self.local:
            raise ValueError("Cannot fetch local identities")
        self.actor_uri = None
        self.inbox_uri = None
        self.profile_uri = None
        # Go knock on webfinger and see what their address is
        await self.fetch_webfinger()
        # Fetch actor JSON
        if self.actor_uri:
            await self.fetch_actor()
        self.fetched = timezone.now()
        await sync_to_async(self.save)()

    async def fetch_webfinger(self) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{self.domain}/.well-known/webfinger?resource=acct:{self.handle}",
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
        if response.status_code >= 400:
            return False
        data = response.json()
        for link in data["links"]:
            if (
                link.get("type") == "application/activity+json"
                and link.get("rel") == "self"
            ):
                self.actor_uri = link["href"]
            elif (
                link.get("type") == "text/html"
                and link.get("rel") == "http://webfinger.net/rel/profile-page"
            ):
                self.profile_uri = link["href"]
        return True

    async def fetch_actor(self) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.actor_uri,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
            if response.status_code >= 400:
                return False
            document = canonicalise(response.json())
            self.name = document.get("name")
            self.inbox_uri = document.get("inbox")
            self.outbox_uri = document.get("outbox")
            self.summary = document.get("summary")
            self.manually_approves_followers = document.get(
                "as:manuallyApprovesFollowers"
            )
            self.public_key = document.get("publicKey", {}).get("publicKeyPem")
            self.icon_uri = document.get("icon", {}).get("url")
            self.image_uri = document.get("image", {}).get("url")
        return True

    def sign(self, cleartext: str) -> str:
        if not self.private_key:
            raise ValueError("Cannot sign - no private key")
        private_key = serialization.load_pem_private_key(
            self.private_key,
            password=None,
        )
        return base64.b64encode(
            private_key.sign(
                cleartext,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        ).decode("ascii")

    def verify_signature(self, crypttext: str, cleartext: str) -> bool:
        if not self.public_key:
            raise ValueError("Cannot verify - no private key")
        public_key = serialization.load_pem_public_key(self.public_key)
        try:
            public_key.verify(
                crypttext,
                cleartext,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except InvalidSignature:
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
        ] = f'keyId="https://{settings.DEFAULT_DOMAIN}{self.urls.actor}",headers="{headers_string}",signature="{signature}"'
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
        return self.name or self.handle

    class urls(urlman.Urls):
        view = "/@{self.short_handle}/"
        actor = "{view}actor/"
        inbox = "{actor}inbox/"
        activate = "{view}activate/"
