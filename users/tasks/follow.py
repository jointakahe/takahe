from core.ld import canonicalise
from core.signatures import HttpSignature
from users.models import Follow


async def handle_follow_request(task_handler):
    """
    Request a follow from a remote server
    """
    follow = await Follow.objects.select_related(
        "source", "source__domain", "target"
    ).aget(pk=task_handler.subject)
    # Construct the request
    request = canonicalise(
        {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": follow.uri,
            "type": "Follow",
            "actor": follow.source.actor_uri,
            "object": follow.target.actor_uri,
        }
    )
    # Sign it and send it
    response = await HttpSignature.signed_request(
        follow.target.inbox_uri, request, follow.source
    )
    if response.status_code >= 400:
        raise ValueError(f"Request error: {response.status_code} {response.content}")
    await Follow.objects.filter(pk=follow.pk).aupdate(requested=True)
