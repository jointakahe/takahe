from asgiref.sync import sync_to_async

from users.models import Follow, Identity


async def handle_inbox_item(task_handler):
    type = task_handler.payload["type"].lower()
    if type == "follow":
        await inbox_follow(task_handler.payload)
    elif type == "accept":
        inner_type = task_handler.payload["object"]["type"].lower()
        if inner_type == "follow":
            await sync_to_async(accept_follow)(task_handler.payload["object"])
        else:
            raise ValueError(f"Cannot handle activity of type accept.{inner_type}")
    elif type == "undo":
        inner_type = task_handler.payload["object"]["type"].lower()
        if inner_type == "follow":
            await inbox_unfollow(task_handler.payload["object"])
        else:
            raise ValueError(f"Cannot handle activity of type undo.{inner_type}")
    else:
        raise ValueError(f"Cannot handle activity of type {inner_type}")


async def inbox_follow(payload):
    """
    Handles an incoming follow request
    """
    # TODO: Manually approved follows
    source = Identity.by_actor_uri_with_create(payload["actor"])
    target = Identity.by_actor_uri(payload["object"])
    # See if this follow already exists
    try:
        follow = Follow.objects.get(source=source, target=target)
    except Follow.DoesNotExist:
        follow = Follow.objects.create(source=source, target=target, uri=payload["id"])
    # See if we need to acknowledge it
    if not follow.acknowledged:
        pass


async def inbox_unfollow(payload):
    pass


def accept_follow(payload):
    """
    Another server has acknowledged our follow request
    """
    source = Identity.by_actor_uri_with_create(payload["actor"])
    target = Identity.by_actor_uri(payload["object"])
    follow = Follow.maybe_get(source, target)
    if follow:
        follow.accepted = True
        follow.save()
