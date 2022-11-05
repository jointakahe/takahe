import base64
import uuid
from functools import partial

import httpx
import urlman
from asgiref.sync import sync_to_async
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.http import http_date

from core.ld import LDDocument


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

    actor_uri = models.CharField(max_length=500, blank=True, null=True)
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

    @property
    def short_handle(self):
        if self.handle.endswith("@" + settings.DEFAULT_DOMAIN):
            return self.handle.split("@", 1)[0]
        return self.handle

    @property
    def domain(self):
        return self.handle.split("@", 1)[1]

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
            )
            if response.status_code >= 400:
                return False
            data = response.json()
            document = LDDocument(data)
            for person in document.by_type(
                "https://www.w3.org/ns/activitystreams#Person"
            ):
                self.name = person.get("https://www.w3.org/ns/activitystreams#name")
                self.summary = person.get(
                    "https://www.w3.org/ns/activitystreams#summary"
                )
                self.inbox_uri = person.get("http://www.w3.org/ns/ldp#inbox")
                self.outbox_uri = person.get(
                    "https://www.w3.org/ns/activitystreams#outbox"
                )
                self.manually_approves_followers = person.get(
                    "https://www.w3.org/ns/activitystreams#manuallyApprovesFollowers'"
                )
                self.private_key = person.get(
                    "https://w3id.org/security#publicKey"
                ).get("https://w3id.org/security#publicKeyPem")
                icon = person.get("https://www.w3.org/ns/activitystreams#icon")
                if icon:
                    self.icon_uri = icon.get(
                        "https://www.w3.org/ns/activitystreams#url"
                    )
                image = person.get("https://www.w3.org/ns/activitystreams#image")
                if image:
                    self.image_uri = image.get(
                        "https://www.w3.org/ns/activitystreams#url"
                    )
        return True

    async def signed_request(self, host, method, path, document):
        """
        Delivers the document to the specified host, method, path and signed
        as this user.
        """
        private_key = serialization.load_pem_private_key(
            self.private_key,
            password=None,
        )
        date_string = http_date(timezone.now().timestamp())
        headers = {
            "(request-target)": f"{method} {path}",
            "Host": host,
            "Date": date_string,
        }
        headers_string = " ".join(headers.keys())
        signed_string = "\n".join(f"{name}: {value}" for name, value in headers.items())
        signature = base64.b64encode(
            private_key.sign(
                signed_string,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        )
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
