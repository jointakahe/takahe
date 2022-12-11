from activities.models import Post, PostInteraction, TimelineEvent

from .. import schemas
from ..decorators import identity_required
from .base import api_router


@api_router.get("/v1/timelines/home", response=list[schemas.Status])
@identity_required
def home(
    request,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    if limit > 40:
        limit = 40
    events = (
        TimelineEvent.objects.filter(
            identity=request.identity,
            type__in=[TimelineEvent.Types.post],
        )
        .select_related("subject_post", "subject_post__author")
        .prefetch_related("subject_post__attachments")
        .order_by("-created")
    )
    if max_id:
        anchor_post = Post.objects.get(pk=max_id)
        events = events.filter(created__lt=anchor_post.created)
    if since_id:
        anchor_post = Post.objects.get(pk=since_id)
        events = events.filter(created__gt=anchor_post.created)
    if min_id:
        # Min ID requires LIMIT events _immediately_ newer than specified, so we
        # invert the ordering to accomodate
        anchor_post = Post.objects.get(pk=min_id)
        events = events.filter(created__gt=anchor_post.created).order_by("created")
    events = list(events[:limit])
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
    if limit > 40:
        limit = 40
    posts = (
        Post.objects.public()
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-created")
    )
    if local:
        posts = posts.filter(local=True)
    elif remote:
        posts = posts.filter(local=False)
    if only_media:
        posts = posts.filter(attachments__id__isnull=True)
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
    posts = list(posts[:limit])
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
    posts = (
        Post.objects.public()
        .tagged_with(hashtag)
        .select_related("author")
        .prefetch_related("attachments")
        .order_by("-created")
    )
    if local:
        posts = posts.filter(local=True)
    if only_media:
        posts = posts.filter(attachments__id__isnull=True)
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
    posts = list(posts[:limit])
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
