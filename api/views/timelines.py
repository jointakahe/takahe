from django.http import HttpRequest, HttpResponse, JsonResponse

from activities.models import Post, PostInteraction
from activities.services import TimelineService
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router
from core.models import Config


@api_router.get("/v1/timelines/home", response=list[schemas.Status])
@identity_required
def home(
    request: HttpRequest,
    response: HttpResponse,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    paginator = MastodonPaginator(Post)
    queryset = TimelineService(request.identity).home()
    pager = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_event_interactions(
        pager.results, request.identity
    )

    if pager.results:
        response.headers["Link"] = pager.link_header(request, ["limit"])

    return [
        event.to_mastodon_status_json(interactions=interactions)
        for event in pager.results
    ]


@api_router.get("/v1/timelines/public", response=list[schemas.Status])
def public(
    request: HttpRequest,
    response: HttpResponse,
    local: bool = False,
    remote: bool = False,
    only_media: bool = False,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    if not request.identity and not Config.system.public_timeline:
        return JsonResponse({"error": "public timeline is disabled"}, status=422)

    if local:
        queryset = TimelineService(request.identity).local()
    else:
        queryset = TimelineService(request.identity).federated()
    if remote:
        queryset = queryset.filter(local=False)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    paginator = MastodonPaginator(Post)
    pager = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )

    if pager.results:
        response.headers["Link"] = pager.link_header(
            request,
            ["limit", "local", "remote", "only_media"],
        )

    interactions = PostInteraction.get_post_interactions(
        pager.results, request.identity
    )
    return [post.to_mastodon_json(interactions=interactions) for post in pager.results]


@api_router.get("/v1/timelines/tag/{hashtag}", response=list[schemas.Status])
@identity_required
def hashtag(
    request: HttpRequest,
    response: HttpResponse,
    hashtag: str,
    local: bool = False,
    only_media: bool = False,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    if limit > 40:
        limit = 40
    queryset = TimelineService(request.identity).hashtag(hashtag)
    if local:
        queryset = queryset.filter(local=True)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    paginator = MastodonPaginator(Post)
    pager = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )

    if pager.results:
        response.headers["Link"] = pager.link_header(
            request,
            ["limit", "local", "remote", "only_media"],
        )

    interactions = PostInteraction.get_post_interactions(
        pager.results, request.identity
    )
    return [post.to_mastodon_json(interactions=interactions) for post in pager.results]


@api_router.get("/v1/conversations", response=list[schemas.Status])
@identity_required
def conversations(
    request: HttpRequest,
    response: HttpResponse,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    # We don't implement this yet
    return []
