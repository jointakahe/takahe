from asgiref.sync import sync_to_async
from django.db import models

from stator.models import State, StateField, StateGraph, StatorModel


class InboxMessageStates(StateGraph):
    received = State(try_interval=300)
    processed = State()

    received.transitions_to(processed)

    @classmethod
    async def handle_received(cls, instance: "InboxMessage"):
        from activities.models import Post, PostInteraction
        from users.models import Follow, Identity

        match instance.message_type:
            case "follow":
                await sync_to_async(Follow.handle_request_ap)(instance.message)
            case "announce":
                await sync_to_async(PostInteraction.handle_ap)(instance.message)
            case "like":
                await sync_to_async(PostInteraction.handle_ap)(instance.message)
            case "create":
                match instance.message_object_type:
                    case "note":
                        await sync_to_async(Post.handle_create_ap)(instance.message)
                    case unknown:
                        raise ValueError(
                            f"Cannot handle activity of type create.{unknown}"
                        )
            case "update":
                match instance.message_object_type:
                    case "note":
                        await sync_to_async(Post.handle_update_ap)(instance.message)
                    case "person":
                        await sync_to_async(Identity.handle_update_ap)(instance.message)
                    case unknown:
                        raise ValueError(
                            f"Cannot handle activity of type update.{unknown}"
                        )
            case "accept":
                match instance.message_object_type:
                    case "follow":
                        await sync_to_async(Follow.handle_accept_ap)(instance.message)
                    case unknown:
                        raise ValueError(
                            f"Cannot handle activity of type accept.{unknown}"
                        )
            case "undo":
                match instance.message_object_type:
                    case "follow":
                        await sync_to_async(Follow.handle_undo_ap)(instance.message)
                    case "like":
                        await sync_to_async(PostInteraction.handle_undo_ap)(
                            instance.message
                        )
                    case "announce":
                        await sync_to_async(PostInteraction.handle_undo_ap)(
                            instance.message
                        )
                    case unknown:
                        raise ValueError(
                            f"Cannot handle activity of type undo.{unknown}"
                        )
            case "delete":
                # If there is no object type, it's probably a profile
                if not isinstance(instance.message["object"], dict):
                    await sync_to_async(Identity.handle_delete_ap)(instance.message)
                else:
                    match instance.message_object_type:
                        case "tombstone":
                            await sync_to_async(Post.handle_delete_ap)(instance.message)
                        case unknown:
                            raise ValueError(
                                f"Cannot handle activity of type delete.{unknown}"
                            )
            case unknown:
                raise ValueError(f"Cannot handle activity of type {unknown}")
        return cls.processed


class InboxMessage(StatorModel):
    """
    an incoming inbox message that needs processing.

    Yes, this is kind of its own message queue built on the state graph system.
    It's fine. It'll scale up to a decent point.
    """

    message = models.JSONField()

    state = StateField(InboxMessageStates)

    @property
    def message_type(self):
        return self.message["type"].lower()

    @property
    def message_object_type(self):
        return self.message["object"]["type"].lower()

    @property
    def message_actor(self):
        return self.message.get("actor")
