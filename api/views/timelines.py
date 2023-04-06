from django.http import HttpRequest
from hatchway import ApiError, ApiResponse, api_view

from activities.models import Post, TimelineEvent
from activities.services import TimelineService
from api import schemas
from api.decorators import scope_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult
from core.models import Config


@scope_required("read:statuses")
@api_view.get
def home(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> ApiResponse[list[schemas.Status]]:
    # Grab a paginated result set of instances
    paginator = MastodonPaginator()
    queryset = TimelineService(request.identity).home()
    queryset = queryset.select_related(
        "subject_post_interaction__post",
        "subject_post_interaction__post__author",
        "subject_post_interaction__post__author__domain",
    )
    queryset = queryset.prefetch_related(
        "subject_post__mentions__domain",
        "subject_post_interaction__post__attachments",
        "subject_post_interaction__post__mentions",
        "subject_post_interaction__post__emojis",
        "subject_post_interaction__post__mentions__domain",
        "subject_post_interaction__post__author__posts",
    )
    pager: PaginationResult[TimelineEvent] = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
        home=True,
    )
    return PaginatingApiResponse(
        schemas.Status.map_from_timeline_event(pager.results, request.identity),
        request=request,
        include_params=["limit"],
    )


@api_view.get
def public(
    request: HttpRequest,
    local: bool = False,
    remote: bool = False,
    only_media: bool = False,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> ApiResponse[list[schemas.Status]]:
    if not request.identity and not Config.system.public_timeline:
        raise ApiError(error="public timeline is disabled", status=422)

    if local:
        queryset = TimelineService(request.identity).local()
    else:
        queryset = TimelineService(request.identity).federated()
    if remote:
        queryset = queryset.filter(local=False)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    # Grab a paginated result set of instances
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
        include_params=["limit", "local", "remote", "only_media"],
    )


@scope_required("read:statuses")
@api_view.get
def hashtag(
    request: HttpRequest,
    hashtag: str,
    local: bool = False,
    only_media: bool = False,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> ApiResponse[list[schemas.Status]]:
    if limit > 40:
        limit = 40
    queryset = TimelineService(request.identity).hashtag(hashtag.lower())
    if local:
        queryset = queryset.filter(local=True)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    # Grab a paginated result set of instances
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
        include_params=["limit", "local", "remote", "only_media"],
    )


@scope_required("read:conversations")
@api_view.get
def conversations(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> list[schemas.Status]:
    # We don't implement this yet
    return []


@scope_required("read:favourites")
@api_view.get
def favourites(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> ApiResponse[list[schemas.Status]]:
    queryset = TimelineService(request.identity).likes()

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
        include_params=["limit"],
    )
