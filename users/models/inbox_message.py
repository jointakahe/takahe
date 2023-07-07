from django.db import models

from core.exceptions import ActivityPubError
from stator.models import State, StateField, StateGraph, StatorModel


class InboxMessageStates(StateGraph):
    received = State(try_interval=300, delete_after=86400 * 3)
    processed = State(externally_progressed=True, delete_after=86400)
    errored = State(externally_progressed=True, delete_after=86400)

    received.transitions_to(processed)
    received.transitions_to(errored)

    @classmethod
    def handle_received(cls, instance: "InboxMessage"):
        from activities.models import Post, PostInteraction, TimelineEvent
        from users.models import Block, Follow, Identity, Report
        from users.services import IdentityService

        try:
            match instance.message_type:
                case "follow":
                    Follow.handle_request_ap(instance.message)
                case "block":
                    Block.handle_ap(instance.message)
                case "announce":
                    PostInteraction.handle_ap(instance.message)
                case "like":
                    PostInteraction.handle_ap(instance.message)
                case "create":
                    match instance.message_object_type:
                        case "note":
                            if instance.message_object_has_content:
                                Post.handle_create_ap(instance.message)
                            else:
                                # Notes without content are Interaction candidates
                                PostInteraction.handle_ap(instance.message)
                        case "question":
                            Post.handle_create_ap(instance.message)
                        case unknown:
                            if unknown in Post.Types.names:
                                Post.handle_create_ap(instance.message)
                case "update":
                    match instance.message_object_type:
                        case "note":
                            Post.handle_update_ap(instance.message)
                        case "person":
                            Identity.handle_update_ap(instance.message)
                        case "service":
                            Identity.handle_update_ap(instance.message)
                        case "group":
                            Identity.handle_update_ap(instance.message)
                        case "organization":
                            Identity.handle_update_ap(instance.message)
                        case "application":
                            Identity.handle_update_ap(instance.message)
                        case "question":
                            Post.handle_update_ap(instance.message)
                        case unknown:
                            if unknown in Post.Types.names:
                                Post.handle_update_ap(instance.message)
                case "accept":
                    match instance.message_object_type:
                        case "follow":
                            Follow.handle_accept_ap(instance.message)
                        case None:
                            # It's a string object, but these will only be for Follows
                            Follow.handle_accept_ap(instance.message)
                        case unknown:
                            raise ValueError(
                                f"Cannot handle activity of type accept.{unknown}"
                            )
                case "reject":
                    match instance.message_object_type:
                        case "follow":
                            Follow.handle_reject_ap(instance.message)
                        case None:
                            # It's a string object, but these will only be for Follows
                            Follow.handle_reject_ap(instance.message)
                        case unknown:
                            raise ValueError(
                                f"Cannot handle activity of type reject.{unknown}"
                            )
                case "undo":
                    match instance.message_object_type:
                        case "follow":
                            Follow.handle_undo_ap(instance.message)
                        case "block":
                            Block.handle_undo_ap(instance.message)
                        case "like":
                            PostInteraction.handle_undo_ap(instance.message)
                        case "announce":
                            PostInteraction.handle_undo_ap(instance.message)
                        case "http://litepub.social/ns#emojireact":
                            # We're ignoring emoji reactions for now
                            pass
                        case unknown:
                            raise ValueError(
                                f"Cannot handle activity of type undo.{unknown}"
                            )
                case "delete":
                    # If there is no object type, we need to see if it's a profile or a post
                    if not isinstance(instance.message["object"], dict):
                        if Identity.objects.filter(
                            actor_uri=instance.message["object"]
                        ).exists():
                            Identity.handle_delete_ap(instance.message)
                        elif Post.objects.filter(
                            object_uri=instance.message["object"]
                        ).exists():
                            Post.handle_delete_ap(instance.message)
                        else:
                            # It is presumably already deleted
                            pass
                    else:
                        match instance.message_object_type:
                            case "tombstone":
                                Post.handle_delete_ap(instance.message)
                            case "note":
                                Post.handle_delete_ap(instance.message)
                            case unknown:
                                raise ValueError(
                                    f"Cannot handle activity of type delete.{unknown}"
                                )
                case "add":
                    PostInteraction.handle_add_ap(instance.message)
                case "remove":
                    PostInteraction.handle_remove_ap(instance.message)
                case "move":
                    # We're ignoring moves for now
                    pass
                case "http://litepub.social/ns#emojireact":
                    # We're ignoring emoji reactions for now
                    pass
                case "flag":
                    # Received reports
                    Report.handle_ap(instance.message)
                case "__internal__":
                    match instance.message_object_type:
                        case "fetchpost":
                            Post.handle_fetch_internal(instance.message["object"])
                        case "cleartimeline":
                            TimelineEvent.handle_clear_timeline(
                                instance.message["object"]
                            )
                        case "addfollow":
                            IdentityService.handle_internal_add_follow(
                                instance.message["object"]
                            )
                        case unknown:
                            raise ValueError(
                                f"Cannot handle activity of type __internal__.{unknown}"
                            )
                case unknown:
                    raise ValueError(f"Cannot handle activity of type {unknown}")
            return cls.processed
        except ActivityPubError:
            return cls.errored


class InboxMessage(StatorModel):
    """
    an incoming inbox message that needs processing.

    Yes, this is kind of its own message queue built on the state graph system.
    It's fine. It'll scale up to a decent point.
    """

    message = models.JSONField()

    state = StateField(InboxMessageStates)

    @classmethod
    def create_internal(cls, payload):
        """
        Creates an internal action message
        """
        cls.objects.create(
            message={
                "type": "__internal__",
                "object": payload,
            }
        )

    @property
    def message_type(self):
        return self.message["type"].lower()

    @property
    def message_object_type(self) -> str | None:
        if isinstance(self.message["object"], dict):
            return self.message["object"]["type"].lower()
        else:
            return None

    @property
    def message_type_full(self):
        if isinstance(self.message.get("object"), dict):
            return f"{self.message_type}.{self.message_object_type}"
        else:
            return f"{self.message_type}"

    @property
    def message_actor(self):
        return self.message.get("actor")

    @property
    def message_object_has_content(self):
        object = self.message.get("object", {})
        return "content" in object or "contentMap" in object
