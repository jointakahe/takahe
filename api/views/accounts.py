from django.shortcuts import get_object_or_404

from activities.models import Post, PostInteraction
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router
from users.models import Identity


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
    queryset = (
        identity.posts.not_hidden()
        .unlisted(include_replies=not exclude_replies)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-created")
    )
    if pinned:
        return []
    if only_media:
        queryset = queryset.filter(attachments__pk__isnull=False)
    if tagged:
        queryset = queryset.tagged_with(tagged)
    paginator = MastodonPaginator(Post)
    posts = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_post_interactions(posts, request.identity)
    return [post.to_mastodon_json(interactions=interactions) for post in queryset]
