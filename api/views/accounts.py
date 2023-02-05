from typing import Any

from django.core.files import File
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from activities.models import Post
from activities.services import SearchService
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult
from core.models import Config
from hatchway import ApiResponse, QueryOrBody, api_view
from users.models import Identity
from users.services import IdentityService
from users.shortcuts import by_handle_or_404


@identity_required
@api_view.get
def verify_credentials(request) -> schemas.Account:
    return schemas.Account.from_identity(request.identity, source=True)


@identity_required
@api_view.patch
def update_credentials(
    request,
    display_name: QueryOrBody[str | None] = None,
    note: QueryOrBody[str | None] = None,
    discoverable: QueryOrBody[bool | None] = None,
    source: QueryOrBody[dict[str, Any] | None] = None,
    fields_attributes: QueryOrBody[dict[str, dict[str, str]] | None] = None,
    avatar: File | None = None,
    header: File | None = None,
) -> schemas.Account:
    identity = request.identity
    service = IdentityService(identity)
    if display_name is not None:
        identity.name = display_name
    if note is not None:
        service.set_summary(note)
    if discoverable is not None:
        identity.discoverable = discoverable
    if source:
        if "privacy" in source:
            privacy_map = {
                "public": Post.Visibilities.public,
                "unlisted": Post.Visibilities.unlisted,
                "private": Post.Visibilities.followers,
                "direct": Post.Visibilities.mentioned,
            }
            Config.set_identity(
                identity,
                "default_post_visibility",
                privacy_map[source["privacy"]],
            )
    if fields_attributes:
        identity.metadata = []
        for attribute in fields_attributes.values():
            attr_name = attribute.get("name", None)
            attr_value = attribute.get("value", None)
            if attr_name:
                # Empty value means delete this item
                if not attr_value:
                    break
                identity.metadata.append({"name": attr_name, "value": attr_value})
    if avatar:
        service.set_icon(avatar)
    if header:
        service.set_image(header)
    identity.save()
    return schemas.Account.from_identity(identity, source=True)


@identity_required
@api_view.get
def account_relationships(request, id: list[str] | None) -> list[schemas.Relationship]:
    result = []
    # ID is actually a list. Thanks Mastodon!
    ids = id or []
    for actual_id in ids:
        identity = get_object_or_404(Identity, pk=actual_id)
        result.append(
            IdentityService(identity).mastodon_json_relationship(request.identity)
        )
    return result


@identity_required
@api_view.get
def familiar_followers(
    request, id: list[str] | None
) -> list[schemas.FamiliarFollowers]:
    """
    Returns people you follow that also follow given account IDs
    """
    ids = id or []
    result = []
    for actual_id in ids:
        target_identity = get_object_or_404(Identity, pk=actual_id)
        result.append(
            schemas.FamiliarFollowers(
                id=actual_id,
                accounts=[
                    schemas.Account.from_identity(identity)
                    for identity in Identity.objects.filter(
                        inbound_follows__source=request.identity,
                        outbound_follows__target=target_identity,
                    )[:20]
                ],
            )
        )
    return result


@identity_required
@api_view.get
def accounts_search(
    request,
    q: str,
    resolve: bool = False,
    following: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[schemas.Account]:
    """
    Handles searching for accounts by username or handle
    """
    if limit > 40:
        limit = 40
    if offset:
        return []
    searcher = SearchService(q, request.identity)
    search_result = searcher.search_identities_handle()
    return [schemas.Account.from_identity(i) for i in search_result]


@api_view.get
def lookup(request: HttpRequest, acct: str) -> schemas.Account:
    """
    Quickly lookup a username to see if it is available, skipping WebFinger
    resolution.
    """
    identity = by_handle_or_404(request, handle=acct, local=False)
    return schemas.Account.from_identity(identity)


@api_view.get
@identity_required
def account(request, id: str) -> schemas.Account:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked),
        pk=id,
    )
    return schemas.Account.from_identity(identity)


@api_view.get
@identity_required
def account_statuses(
    request: HttpRequest,
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
) -> ApiResponse[list[schemas.Status]]:
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
        return ApiResponse([])
    if only_media:
        queryset = queryset.filter(attachments__pk__isnull=False)
    if tagged:
        queryset = queryset.tagged_with(tagged)
    # Get user posts with pagination
    paginator = MastodonPaginator()
    pager: PaginationResult[Post] = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    return PaginatingApiResponse(
        schemas.Status.map_from_post(pager.results, request.identity),
        request=request,
        include_params=[
            "limit",
            "id",
            "exclude_reblogs",
            "exclude_replies",
            "only_media",
            "pinned",
            "tagged",
        ],
    )


@api_view.post
@identity_required
def account_follow(request, id: str, reblogs: bool = True) -> schemas.Relationship:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(identity)
    service.follow_from(request.identity, boosts=reblogs)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@api_view.post
@identity_required
def account_unfollow(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(identity)
    service.unfollow_from(request.identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@api_view.post
@identity_required
def account_block(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(identity)
    service.block_from(request.identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@api_view.post
@identity_required
def account_unblock(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(identity)
    service.unblock_from(request.identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@identity_required
@api_view.post
def account_mute(
    request,
    id: str,
    notifications: QueryOrBody[bool] = True,
    duration: QueryOrBody[int] = 0,
) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(identity)
    service.mute_from(
        request.identity,
        duration=duration,
        include_notifications=notifications,
    )
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@identity_required
@api_view.post
def account_unmute(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(identity)
    service.unmute_from(request.identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@api_view.get
def account_following(
    request: HttpRequest,
    id: str,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 40,
) -> ApiResponse[list[schemas.Account]]:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )

    if not identity.config_identity.visible_follows and request.identity != identity:
        return ApiResponse([])

    service = IdentityService(identity)

    paginator = MastodonPaginator(max_limit=80)
    pager: PaginationResult[Identity] = paginator.paginate(
        service.following(),
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    return PaginatingApiResponse(
        [schemas.Account.from_identity(i) for i in pager.results],
        request=request,
        include_params=["limit"],
    )


@api_view.get
def account_followers(
    request: HttpRequest,
    id: str,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 40,
) -> ApiResponse[list[schemas.Account]]:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )

    if not identity.config_identity.visible_follows and request.identity != identity:
        return ApiResponse([])

    service = IdentityService(identity)

    paginator = MastodonPaginator(max_limit=80)
    pager: PaginationResult[Identity] = paginator.paginate(
        service.followers(),
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    return PaginatingApiResponse(
        [schemas.Account.from_identity(i) for i in pager.results],
        request=request,
        include_params=["limit"],
    )
