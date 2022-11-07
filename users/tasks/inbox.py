from users.models import Follow, Identity


async def handle_inbox_item(task_handler):
    type = task_handler.payload["type"].lower()
    if type == "follow":
        await inbox_follow(task_handler.payload)
    elif type == "undo":
        inner_type = task_handler.payload["object"]["type"].lower()
        if inner_type == "follow":
            await inbox_unfollow(task_handler.payload["object"])
        else:
            raise ValueError("Cannot undo activity of type {inner_type}")
    else:
        raise ValueError("Cannot handle activity of type {inner_type}")


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
