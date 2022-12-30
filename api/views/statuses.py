from typing import Literal

from django.forms import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Schema

from activities.models import (
    Post,
    PostAttachment,
    PostInteraction,
    PostInteractionStates,
    TimelineEvent,
)
from activities.services import PostService
from api import schemas
from api.views.base import api_router
from core.models import Config
from users.models import Identity

from ..decorators import identity_required
from ..pagination import MastodonPaginator


class PostStatusSchema(Schema):
    status: str
    in_reply_to_id: str | None = None
    sensitive: bool = False
    spoiler_text: str | None = None
    visibility: Literal["public", "unlisted", "private", "direct"] = "public"
    language: str | None = None
    scheduled_at: str | None = None
    media_ids: list[str] = []


@api_router.post("/v1/statuses", response=schemas.Status)
@identity_required
def post_status(request, details: PostStatusSchema):
    # Check text length
    if len(details.status) > Config.system.post_length:
        raise ValidationError("Status is too long")
    if len(details.status) == 0 and not details.media_ids:
        raise ValidationError("Status is empty")
    # Grab attachments
    attachments = [get_object_or_404(PostAttachment, pk=id) for id in details.media_ids]
    # Create the Post
    visibility_map = {
        "public": Post.Visibilities.public,
        "unlisted": Post.Visibilities.unlisted,
        "private": Post.Visibilities.followers,
        "direct": Post.Visibilities.mentioned,
    }
    reply_post = None
    if details.in_reply_to_id:
        try:
            reply_post = Post.objects.get(pk=details.in_reply_to_id)
        except Post.DoesNotExist:
            pass
    post = Post.create_local(
        author=request.identity,
        content=details.status,
        summary=details.spoiler_text,
        sensitive=details.sensitive,
        visibility=visibility_map[details.visibility],
        reply_to=reply_post,
        attachments=attachments,
    )
    # Add their own timeline event for immediate visibility
    TimelineEvent.add_post(request.identity, post)
    return post.to_mastodon_json()


@api_router.get("/v1/statuses/{id}", response=schemas.Status)
@identity_required
def status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.delete("/v1/statuses/{id}", response=schemas.Status)
@identity_required
def delete_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    PostService(post).delete()
    return post.to_mastodon_json()


@api_router.get("/v1/statuses/{id}/context", response=schemas.Context)
@identity_required
def status_context(request, id: str):
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    ancestors, descendants = service.context(request.identity)
    interactions = PostInteraction.get_post_interactions(
        ancestors + descendants, request.identity
    )
    return {
        "ancestors": [
            p.to_mastodon_json(interactions=interactions) for p in reversed(ancestors)
        ],
        "descendants": [
            p.to_mastodon_json(interactions=interactions) for p in descendants
        ],
    }


@api_router.post("/v1/statuses/{id}/favourite", response=schemas.Status)
@identity_required
def favourite_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.like_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.post("/v1/statuses/{id}/unfavourite", response=schemas.Status)
@identity_required
def unfavourite_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.unlike_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.get("/v1/statuses/{id}/favourited_by", response=list[schemas.Account])
def favourited_by(
    request: HttpRequest,
    response: HttpResponse,
    id: str,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
):
    """
    View who favourited a given status.
    """
    # This method should filter out private statuses, but we don't really have
    # a concept of "private status" yet.
    post = get_object_or_404(Post, pk=id)

    paginator = MastodonPaginator(Identity, sort_attribute="published")
    pager = paginator.paginate(
        post.interactions.filter(
            type=PostInteraction.Types.like,
            state__in=PostInteractionStates.group_active(),
        )
        .select_related("identity")
        .order_by("published"),
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )

    if pager.results:
        response.headers["Link"] = pager.link_header(
            request,
            ["limit"],
        )

    return [result.identity.to_mastodon_json() for result in pager.results]


@api_router.post("/v1/statuses/{id}/reblog", response=schemas.Status)
@identity_required
def reblog_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.boost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.post("/v1/statuses/{id}/unreblog", response=schemas.Status)
@identity_required
def unreblog_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.unboost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)
