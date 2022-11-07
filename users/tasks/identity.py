from asgiref.sync import sync_to_async

from users.models import Identity


async def handle_identity_fetch(task_handler):
    # Get the actor URI via webfinger
    actor_uri, handle = await Identity.fetch_webfinger(task_handler.subject)
    # Get or create the identity, then fetch
    identity = await sync_to_async(Identity.by_actor_uri_with_create)(actor_uri)
    await identity.fetch_actor()
