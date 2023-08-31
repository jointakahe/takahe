from django.conf import settings

from core.signatures import RsaKeys


class RelayActor:
    """
    Pesudo actor for subscribing relay services from local instance

    Relay services typically supports two modes: Mastodon and LitePub.

    in Mastodon mode:
    instance handshake with relay by sending Follow[1] to relay's inbox, relay won't follow back
    instance publishes its activities by sending Create/Update/Delete to relay's inbox
    relay publishes remote activities by sending Announce to instance's inbox

    in LitePub mode (also known as Pleroma mode):
    instance queries relay server's actor uri, sends Follow to relay's inbox and gets Follow back
    instance publishes its activities by sending Announce[2] to relay's inbox
    relay publishes remote activities by sending Announce to instance's inbox

    Our implementation do initial handshake in LitePub mode, then send activities in Mastodon mode;
    Most if not all modern relay implementations seem fine with this mixed mode

    [1] in this Follow and its Accept/Reject, target actor uri is unknown, "object" has to be
        "https://www.w3.org/ns/activitystreams#Public"
    [2] in this Announce, "to" has to be the relay's actor uri
    [3] various implementation has strict validations, e.g.
        instance actor uri has to ends with "/relay"
        instance actor type must be Application
        "to":"as:Public" must become "to":["https://www.w3.org/ns/activitystreams#Public"]
    """

    actor_uri = f"https://{settings.MAIN_DOMAIN}/relay"
    inbox_uri = f"https://{settings.MAIN_DOMAIN}/inbox/"
    handle = f"__relay__@{settings.MAIN_DOMAIN}"
    _private_key = None
    _public_key = None

    @classmethod
    def subscribe(cls, relay_uri):
        from .inbox_message import InboxMessage

        InboxMessage.create_internal(
            {
                "type": "AddFollow",
                "source": cls.get_identity().pk,
                "target_actor": relay_uri,
                "boosts": False,
            }
        )

    @classmethod
    def unsubscribe(cls, relay_uri):
        from .inbox_message import InboxMessage

        InboxMessage.create_internal(
            {
                "type": "UnfollowRelay",
                "actor_uri": relay_uri,
            }
        )

    @classmethod
    def remove(cls, relay_uri):
        from .follow import Follow

        Follow.objects.filter(
            source__actor_uri=cls.actor_uri, target__actor_uri=relay_uri
        ).delete()
        Follow.objects.filter(
            target__actor_uri=cls.actor_uri, source__actor_uri=relay_uri
        ).delete()

    @classmethod
    def handle_internal_unfollow(cls, payload):
        """
        Handles actual unfollow from relay and remove queued fanout
        """
        from activities.models import FanOut, FanOutStates

        from ..services.identity import IdentityService
        from .identity import Identity

        relay_uri = payload["actor_uri"]
        relay = Identity.objects.get(actor_uri=relay_uri)
        svc = IdentityService(cls.get_identity())
        svc.unfollow(relay)
        svc.reject_follow_request(relay)
        FanOut.transition_perform_queryset(
            FanOut.objects.filter(identity=relay), FanOutStates.skipped
        )

    @classmethod
    def get_identity(cls):
        from users.models import Identity

        return Identity.objects.get(actor_uri=cls.actor_uri)

    @classmethod
    def get_relays(cls):
        from .follow import FollowStates
        from .identity import Identity

        return Identity.objects.not_deleted().filter(
            inbound_follows__source=cls.get_identity(),
            inbound_follows__state=FollowStates.accepted,
        )

    @classmethod
    def initialize_if_needed(cls):
        from users.models import Identity

        if not Identity.objects.filter(actor_uri=cls.actor_uri).exists():
            _private_key, _public_key = RsaKeys.generate_keypair()
            Identity.objects.create(
                username="__relay__",
                # domain_id= settings.MAIN_DOMAIN,
                name="System Relay Actor",
                actor_uri=cls.actor_uri,
                actor_type="Application",
                local=True,
                discoverable=False,
                manually_approves_followers=False,
                private_key=_private_key,
                public_key=_public_key,
                public_key_id=cls.actor_uri + "#main-key",
                inbox_uri=cls.inbox_uri,
                shared_inbox_uri=cls.inbox_uri,
            )

    @classmethod
    def to_ap(cls):
        identity = cls.get_identity()
        return {
            "id": identity.actor_uri,
            "type": identity.actor_type,
            "inbox": identity.shared_inbox_uri,
            # "outbox": identity.outbox_uri,
            "endpoints": {
                "sharedInbox": identity.shared_inbox_uri,
            },
            "preferredUsername": identity.username,
            "name": identity.name,
            "manuallyApprovesFollowers": identity.manually_approves_followers,
            "toot:discoverable": identity.discoverable,
            "publicKey": {
                "id": identity.public_key_id,
                "owner": identity.actor_uri,
                "publicKeyPem": identity.public_key,
            },
        }

    def to_webfinger(self):
        return {
            "subject": f"acct:{self.handle}",
            "links": [
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": self.actor_uri,
                },
            ],
        }
