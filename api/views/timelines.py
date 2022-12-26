from activities.models import Post, PostInteraction, TimelineEvent
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router
from users.models import Identity


@api_router.get("/v1/timelines/home", response=list[schemas.Status])
@identity_required
def home(
    request,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    paginator = MastodonPaginator(Post)
    queryset = (
        TimelineEvent.objects.filter(
            identity=request.identity,
            type__in=[TimelineEvent.Types.post],
        )
        .select_related("subject_post", "subject_post__author")
        .prefetch_related("subject_post__attachments")
        .order_by("-published")
    )
    events = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_event_interactions(events, request.identity)
    return [
        event.subject_post.to_mastodon_json(interactions=interactions)
        for event in events
    ]


@api_router.get("/v1/timelines/public", response=list[schemas.Status])
@identity_required
def public(
    request,
    local: bool = False,
    remote: bool = False,
    only_media: bool = False,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    queryset = (
        Post.objects.public()
        .filter(author__restriction=Identity.Restriction.none)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-published")
    )
    if local:
        queryset = queryset.filter(local=True)
    elif remote:
        queryset = queryset.filter(local=False)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    paginator = MastodonPaginator(Post)
    posts = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_post_interactions(posts, request.identity)
    return [post.to_mastodon_json(interactions=interactions) for post in posts]


@api_router.get("/v1/timelines/tag/{hashtag}", response=list[schemas.Status])
@identity_required
def hashtag(
    request,
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
    queryset = (
        Post.objects.public()
        .filter(author__restriction=Identity.Restriction.none)
        .tagged_with(hashtag)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-published")
    )
    if local:
        queryset = queryset.filter(local=True)
    if only_media:
        queryset = queryset.filter(attachments__id__isnull=True)
    paginator = MastodonPaginator(Post)
    posts = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_post_interactions(posts, request.identity)
    return [post.to_mastodon_json(interactions=interactions) for post in posts]


@api_router.get("/v1/conversations", response=list[schemas.Status])
@identity_required
def conversations(
    request,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    # We don't implement this yet
    return []
