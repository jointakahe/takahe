from typing import Any

from django.core.files import File
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from hatchway import ApiResponse, QueryOrBody, api_view

from activities.models import Post, PostInteraction, PostInteractionStates
from activities.services import SearchService
from api import schemas
from api.decorators import scope_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult
from core.models import Config
from users.models import Identity, IdentityStates
from users.services import IdentityService
from users.shortcuts import by_handle_or_404


@scope_required("read")
@api_view.get
def verify_credentials(request) -> schemas.Account:
    return schemas.Account.from_identity(request.identity, source=True)


@scope_required("write")
@api_view.patch
def update_credentials(
    request,
    display_name: QueryOrBody[str | None] = None,
    note: QueryOrBody[str | None] = None,
    discoverable: QueryOrBody[bool | None] = None,
    locked: QueryOrBody[bool | None] = None,
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
    if locked is not None:
        identity.manually_approves_followers = locked
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
    identity.transition_perform(IdentityStates.edited)
    return schemas.Account.from_identity(identity, source=True)


@scope_required("read")
@api_view.get
def account_relationships(
    request, id: list[str] | str | None
) -> list[schemas.Relationship]:
    result = []
    if isinstance(id, str):
        ids = [id]
    elif id is None:
        ids = []
    else:
        ids = id
    for actual_id in ids:
        identity = get_object_or_404(Identity, pk=actual_id)
        result.append(
            IdentityService(identity).mastodon_json_relationship(request.identity)
        )
    return result


@scope_required("read")
@api_view.get
def familiar_followers(
    request, id: list[str] | str | None
) -> list[schemas.FamiliarFollowers]:
    """
    Returns people you follow that also follow given account IDs
    """
    if isinstance(id, str):
        ids = [id]
    elif id is None:
        ids = []
    else:
        ids = id
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


@scope_required("read")
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


@scope_required("read:accounts")
@api_view.get
def account(request, id: str) -> schemas.Account:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked),
        pk=id,
    )
    return schemas.Account.from_identity(identity)


@scope_required("read:statuses")
@api_view.get
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
        queryset = queryset.filter(
            interactions__type=PostInteraction.Types.pin,
            interactions__state__in=PostInteractionStates.group_active(),
        )
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


@scope_required("write:follows")
@api_view.post
def account_follow(request, id: str, reblogs: bool = True) -> schemas.Relationship:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(request.identity)
    service.follow(identity, boosts=reblogs)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@scope_required("write:follows")
@api_view.post
def account_unfollow(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(
        Identity.objects.exclude(restriction=Identity.Restriction.blocked), pk=id
    )
    service = IdentityService(request.identity)
    service.unfollow(identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@scope_required("write:blocks")
@api_view.post
def account_block(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(request.identity)
    service.block(identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@scope_required("write:blocks")
@api_view.post
def account_unblock(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(request.identity)
    service.unblock(identity)
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@scope_required("write:blocks")
@api_view.post
def account_mute(
    request,
    id: str,
    notifications: QueryOrBody[bool] = True,
    duration: QueryOrBody[int] = 0,
) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(request.identity)
    service.mute(
        identity,
        duration=duration,
        include_notifications=notifications,
    )
    return schemas.Relationship.from_identity_pair(identity, request.identity)


@scope_required("write:blocks")
@api_view.post
def account_unmute(request, id: str) -> schemas.Relationship:
    identity = get_object_or_404(Identity, pk=id)
    service = IdentityService(request.identity)
    service.unmute(identity)
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


@api_view.get
def account_featured_tags(request: HttpRequest, id: str) -> list[schemas.FeaturedTag]:
    # Not implemented yet
    return []
