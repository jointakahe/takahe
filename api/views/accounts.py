from django.shortcuts import get_object_or_404

from activities.models import Post
from api import schemas
from api.views.base import api_router
from users.models import Identity

from ..decorators import identity_required


@api_router.get("/v1/accounts/verify_credentials", response=schemas.Account)
@identity_required
def verify_credentials(request):
    return request.identity.to_mastodon_json()


@api_router.get("/v1/accounts/relationships", response=list[schemas.Relationship])
@identity_required
def account_relationships(request):
    ids = request.GET.getlist("id[]")
    result = []
    for id in ids:
        identity = get_object_or_404(Identity, pk=id)
        result.append(
            {
                "id": identity.pk,
                "following": identity.inbound_follows.filter(
                    source=request.identity
                ).exists(),
                "followed_by": identity.outbound_follows.filter(
                    target=request.identity
                ).exists(),
                "showing_reblogs": True,
                "notifying": False,
                "blocking": False,
                "blocked_by": False,
                "muting": False,
                "muting_notifications": False,
                "requested": False,
                "domain_blocking": False,
                "endorsed": False,
                "note": "",
            }
        )
    return result


@api_router.get("/v1/accounts/{id}", response=schemas.Account)
@identity_required
def account(request, id: str):
    identity = get_object_or_404(Identity, pk=id)
    return identity.to_mastodon_json()


@api_router.get("/v1/accounts/{id}/statuses", response=list[schemas.Status])
@identity_required
def account_statuses(
    request,
    id: str,
    exclude_reblogs: bool = False,
    exclude_replies: bool = False,
    only_media: bool = False,
    pinned: bool = False,
    tagged: str | None = None,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    identity = get_object_or_404(Identity, pk=id)
    posts = (
        identity.posts.public()
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-created")
    )
    if pinned:
        return []
    if only_media:
        posts = posts.filter(attachments__pk__isnull=False)
    if tagged:
        posts = posts.tagged_with(tagged)
    if max_id:
        anchor_post = Post.objects.get(pk=max_id)
        posts = posts.filter(created__lt=anchor_post.created)
    if since_id:
        anchor_post = Post.objects.get(pk=since_id)
        posts = posts.filter(created__gt=anchor_post.created)
    if min_id:
        # Min ID requires LIMIT posts _immediately_ newer than specified, so we
        # invert the ordering to accomodate
        anchor_post = Post.objects.get(pk=min_id)
        posts = posts.filter(created__gt=anchor_post.created).order_by("created")
    return [post.to_mastodon_json() for post in posts[:limit]]
