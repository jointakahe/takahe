from asgiref.sync import sync_to_async
from django.db import models

from stator.models import State, StateField, StateGraph, StatorModel
from users.models import Follow, Identity


class InboxMessageStates(StateGraph):
    received = State(try_interval=300)
    processed = State()

    received.transitions_to(processed)

    @classmethod
    async def handle_received(cls, instance: "InboxMessage"):
        type = instance.message["type"].lower()
        if type == "follow":
            await instance.follow_request()
        elif type == "accept":
            inner_type = instance.message["object"]["type"].lower()
            if inner_type == "follow":
                await instance.follow_accepted()
            else:
                raise ValueError(f"Cannot handle activity of type accept.{inner_type}")
        elif type == "undo":
            inner_type = instance.message["object"]["type"].lower()
            if inner_type == "follow":
                await instance.follow_undo()
            else:
                raise ValueError(f"Cannot handle activity of type undo.{inner_type}")
        else:
            raise ValueError(f"Cannot handle activity of type {type}")


class InboxMessage(StatorModel):
    """
    an incoming inbox message that needs processing.

    Yes, this is kind of its own message queue built on the state graph system.
    It's fine. It'll scale up to a decent point.
    """

    message = models.JSONField()

    state = StateField(InboxMessageStates)

    @sync_to_async
    def follow_request(self):
        """
        Handles an incoming follow request
        """
        Follow.remote_created(
            source=Identity.by_actor_uri_with_create(self.message["actor"]),
            target=Identity.by_actor_uri(self.message["object"]),
            uri=self.message["id"],
        )

    @sync_to_async
    def follow_accepted(self):
        """
        Handles an incoming acceptance of one of our follow requests
        """
        Follow.remote_accepted(
            source=Identity.by_actor_uri_with_create(self.message["actor"]),
            target=Identity.by_actor_uri(self.message["object"]),
        )

    async def follow_undo(self):
        """
        Handles an incoming follow undo
        """
