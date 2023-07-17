from typing import Literal

from django.conf import settings

from core.models import Config
from core.signatures import HttpSignature, RsaKeys


class SystemActor:
    """
    Represents the system actor, that we use to sign all HTTP requests
    that are not on behalf of an Identity.

    Note that this needs Config.system to be set to be initialised.
    """

    def __init__(self):
        self.private_key = Config.system.system_actor_private_key
        self.public_key = Config.system.system_actor_public_key
        self.actor_uri = f"https://{settings.MAIN_DOMAIN}/actor/"
        self.public_key_id = self.actor_uri + "#main-key"
        self.profile_uri = f"https://{settings.MAIN_DOMAIN}/about/"
        self.username = "__system__"
        self.handle = f"__system__@{settings.MAIN_DOMAIN}"

    def absolute_profile_uri(self):
        return self.profile_uri

    def generate_keys(self):
        self.private_key, self.public_key = RsaKeys.generate_keypair()
        Config.set_system("system_actor_private_key", self.private_key)
        Config.set_system("system_actor_public_key", self.public_key)

    @classmethod
    def generate_keys_if_needed(cls):
        # Load the system config into the right place
        Config.system = Config.load_system()
        instance = cls()
        if "-----BEGIN" not in instance.private_key:
            instance.generate_keys()

    def to_ap(self):
        return {
            "id": self.actor_uri,
            "type": "Application",
            "inbox": self.actor_uri + "inbox/",
            "outbox": self.actor_uri + "outbox/",
            "endpoints": {
                "sharedInbox": f"https://{settings.MAIN_DOMAIN}/inbox/",
            },
            "preferredUsername": self.username,
            "url": self.profile_uri,
            "manuallyApprovesFollowers": True,
            "toot:discoverable": False,
            "publicKey": {
                "id": self.public_key_id,
                "owner": self.actor_uri,
                "publicKeyPem": self.public_key,
            },
        }

    def to_webfinger(self):
        return {
            "subject": f"acct:{self.handle}",
            "aliases": [
                self.absolute_profile_uri(),
            ],
            "links": [
                {
                    "rel": "http://webfinger.net/rel/profile-page",
                    "type": "text/html",
                    "href": self.absolute_profile_uri(),
                },
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": self.actor_uri,
                },
            ],
        }

    def signed_request(
        self,
        method: Literal["get", "post"],
        uri: str,
        body: dict | None = None,
    ):
        """
        Performs a signed request on behalf of the System Actor.
        """
        return HttpSignature.signed_request(
            method=method,
            uri=uri,
            body=body,
            private_key=self.private_key,
            key_id=self.public_key_id,
        )
