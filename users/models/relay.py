import logging
import re

from django.db import models

from stator.models import State, StateField, StateGraph, StatorModel
from users.models.system_actor import SystemActor

logger = logging.getLogger(__name__)


class RelayStates(StateGraph):
    new = State(try_interval=600)
    subscribing = State(externally_progressed=True)
    subscribed = State(externally_progressed=True)
    failed = State(externally_progressed=True)
    rejected = State(externally_progressed=True)
    unsubscribing = State(try_interval=600)
    unsubscribed = State(delete_after=1)

    new.transitions_to(subscribing)
    new.transitions_to(unsubscribing)
    new.transitions_to(failed)
    new.times_out_to(failed, seconds=38400)
    subscribing.transitions_to(subscribed)
    subscribing.transitions_to(unsubscribing)
    subscribing.transitions_to(unsubscribed)
    subscribing.transitions_to(rejected)
    subscribing.transitions_to(failed)
    subscribed.transitions_to(unsubscribing)
    subscribed.transitions_to(rejected)
    failed.transitions_to(unsubscribed)
    rejected.transitions_to(unsubscribed)
    unsubscribing.transitions_to(failed)
    unsubscribing.transitions_to(unsubscribed)
    unsubscribing.times_out_to(failed, seconds=38400)

    @classmethod
    def handle_new(cls, instance: "Relay"):
        system_actor = SystemActor()
        try:
            response = system_actor.signed_request(
                method="post",
                uri=instance.inbox_uri,
                body=instance.to_follow_ap(),
            )
        except Exception as e:
            logger.error(f"Error sending follow request: {instance.inbox_uri} {e}")
            return cls.failed
        if response.status_code >= 200 and response.status_code < 300:
            return cls.subscribing
        else:
            logger.error(f"Follow {instance.inbox_uri} HTTP {response.status_code}")
            return cls.failed

    @classmethod
    def handle_unsubscribing(cls, instance: "Relay"):
        system_actor = SystemActor()
        try:
            response = system_actor.signed_request(
                method="post",
                uri=instance.inbox_uri,
                body=instance.to_unfollow_ap(),
            )
        except Exception as e:
            logger.error(f"Error sending unfollow request: {instance.inbox_uri} {e}")
            return cls.failed
        if response.status_code >= 200 and response.status_code < 300:
            return cls.unsubscribed
        else:
            logger.error(f"Unfollow {instance.inbox_uri} HTTP {response.status_code}")
            return cls.failed


class Relay(StatorModel):
    inbox_uri = models.CharField(max_length=500, unique=True)

    state = StateField(RelayStates)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        indexes: list = []

    @classmethod
    def active_inbox_uris(cls):
        return list(
            cls.objects.filter(state=RelayStates.subscribed).values_list(
                "inbox_uri", flat=True
            )
        )

    @classmethod
    def subscribe(cls, inbox_uri: str) -> "Relay":
        return cls.objects.get_or_create(inbox_uri=inbox_uri.strip())[0]

    def unsubscribe(self):
        self.transition_perform(RelayStates.unsubscribing)

    def force_unsubscribe(self):
        self.transition_perform(RelayStates.unsubscribed)

    def to_follow_ap(self):
        system_actor = SystemActor()
        return {  # skip canonicalise here to keep Public addressing as full URI
            "@context": ["https://www.w3.org/ns/activitystreams"],
            "id": f"{system_actor.actor_uri}relay/{self.pk}/#follow",
            "type": "Follow",
            "actor": system_actor.actor_uri,
            "object": "https://www.w3.org/ns/activitystreams#Public",
        }

    def to_unfollow_ap(self):
        system_actor = SystemActor()
        return {  # skip canonicalise here to keep Public addressing as full URI
            "@context": ["https://www.w3.org/ns/activitystreams"],
            "id": f"{system_actor.actor_uri}relay/{self.pk}/#unfollow",
            "type": "Undo",
            "actor": system_actor.actor_uri,
            "object": self.to_follow_ap(),
        }

    @classmethod
    def is_ap_message_for_relay(cls, message) -> bool:
        return (
            re.match(r".+/relay/(\d+)/#(follow|unfollow)$", message["object"]["id"])
            is not None
        )

    @classmethod
    def get_by_ap(cls, message) -> "Relay":
        m = re.match(r".+/relay/(\d+)/#(follow|unfollow)$", message["object"]["id"])
        if not m:
            raise ValueError("Not a valid relay follow response")
        return cls.objects.get(pk=int(m[1]))

    @classmethod
    def handle_accept_ap(cls, message):
        relay = cls.get_by_ap(message)
        relay.transition_perform(RelayStates.subscribed)

    @classmethod
    def handle_reject_ap(cls, message):
        relay = cls.get_by_ap(message)
        relay.transition_perform(RelayStates.rejected)
