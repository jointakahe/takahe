from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from ninja import Field

from activities.services import SearchService
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router
from users.models import Identity
from users.services import IdentityService


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
            IdentityService(identity).mastodon_json_relationship(request.identity)
        )
    return result


@api_router.get(
    "/v1/accounts/familiar_followers", response=list[schemas.FamiliarFollowers]
)
@identity_required
def familiar_followers(request):
    """
    Returns people you follow that also follow given account IDs
    """
    ids = request.GET.getlist("id[]")
    result = []
    for id in ids:
        target_identity = get_object_or_404(Identity, pk=id)
        result.append(
            {
                "id": id,
                "accounts": [
                    identity.to_mastodon_json()
                    for identity in Identity.objects.filter(
                        inbound_follows__source=request.identity,
                        outbound_follows__target=target_identity,
                    )[:20]
                ],
            }
        )
    return result


@api_router.get("/v1/accounts/search", response=list[schemas.Account])
@identity_required
def search(
    request,
    q: str,
    fetch_identities: bool = Field(False, alias="resolve"),
    following: bool = False,
    limit: int = 20,
    offset: int = 0,
):
    """
    Handles searching for accounts by username or handle
    """
    if limit > 40:
        limit = 40
    if offset:
        return []
    searcher = SearchService(q, request.identity)
    search_result = searcher.search_identities_handle()
    return [i.to_mastodon_json() for i in search_result]


@api_router.get("/v1/accounts/lookup", response=schemas.Account)
def lookup(request: HttpRequest, acct: str):
    """
    Quickly lookup a username to see if it is available, skipping WebFinger
    resolution.
    """
    acct = acct.lstrip("@")
    host = request.get_host()

    identity = Identity.objects.filter(
        Q(domain__service_domain__iexact=host) | Q(domain__domain__iexact=host),
        local=True,
        username__iexact=acct,
    ).first()

    if not identity:
        return JsonResponse({"error": "Record not found"}, status=404)

    return identity.to_mastodon_json()


@api_router.get("/v1/accounts/{id}", response=schemas.Account)
@identity_required
def account(request, id: str):
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    return identity.to_mastodon_json()


@api_router.get("/v1/accounts/{id}/statuses", response=list[schemas.Status])
@identity_required
def account_statuses(
    request: HttpRequest,
    response: HttpResponse,
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
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    queryset = (
        identity.posts.not_hidden()
        .unlisted(include_replies=not exclude_replies)
        .select_related("author", "author__domain")
        .prefetch_related(
            "attachments",
            "mentions__domain",
            "emojis",
            "author__inbound_follows",
            "author__outbound_follows",
            "author__posts",
        )
        .order_by("-created")
    )
    if pinned:
        return []
    if only_media:
        queryset = queryset.filter(attachments__pk__isnull=False)
    if tagged:
        queryset = queryset.tagged_with(tagged)
    # Get user posts with pagination
    paginator = MastodonPaginator()
    pager = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    # Convert those to the JSON form
    pager.jsonify_posts(identity=request.identity)
    # Add a link header if we need to
    if pager.results:
        response.headers["Link"] = pager.link_header(
            request,
            [
                "limit",
                "id",
                "exclude_reblogs",
                "exclude_replies",
                "only_media",
                "pinned",
                "tagged",
            ],
        )
    return pager.json_results


@api_router.post("/v1/accounts/{id}/follow", response=schemas.Relationship)
@identity_required
def account_follow(request, id: str, reblogs: bool = True):
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(identity)
    service.follow_from(request.identity, boosts=reblogs)
    return service.mastodon_json_relationship(request.identity)


@api_router.post("/v1/accounts/{id}/unfollow", response=schemas.Relationship)
@identity_required
def account_unfollow(request, id: str):
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(identity)
    service.unfollow_from(request.identity)
    return service.mastodon_json_relationship(request.identity)


@api_router.get("/v1/accounts/{id}/following", response=list[schemas.Account])
def account_following(
    request: HttpRequest,
    response: HttpResponse,
    id: str,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 40,
):
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )

    if not identity.config_identity.visible_follows and request.identity != identity:
        return []

    service = IdentityService(identity)

    paginator = MastodonPaginator(max_limit=80)
    pager = paginator.paginate(
        service.following(),
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    pager.jsonify_identities()

    if pager.results:
        response.headers["Link"] = pager.link_header(
            request,
            ["limit"],
        )

    return pager.json_results
