from typing import Literal

from django.forms import ValidationError
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from activities.models import (
    Post,
    PostAttachment,
    PostInteraction,
    PostInteractionStates,
    TimelineEvent,
)
from activities.services import PostService
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator, PaginationResult
from core.models import Config
from hatchway import ApiResponse, Schema, api_view


class PostStatusSchema(Schema):
    status: str
    in_reply_to_id: str | None = None
    sensitive: bool = False
    spoiler_text: str | None = None
    visibility: Literal["public", "unlisted", "private", "direct"] = "public"
    language: str | None = None
    scheduled_at: str | None = None
    media_ids: list[str] = []


@identity_required
@api_view.post
def post_status(request, details: PostStatusSchema) -> schemas.Status:
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
    return schemas.Status.from_post(post)


@identity_required
@api_view.get
def status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return schemas.Status.from_post(post, interactions=interactions)


@identity_required
@api_view.delete
def delete_status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    PostService(post).delete()
    return schemas.Status.from_post(post)


@identity_required
@api_view.get
def status_context(request, id: str) -> schemas.Context:
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    ancestors, descendants = service.context(request.identity)
    interactions = PostInteraction.get_post_interactions(
        ancestors + descendants, request.identity
    )
    return schemas.Context(
        ancestors=[
            schemas.Status.from_post(p, interactions=interactions)
            for p in reversed(ancestors)
        ],
        descendants=[
            schemas.Status.from_post(p, interactions=interactions) for p in descendants
        ],
    )


@identity_required
@api_view.post
def favourite_status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.like_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return schemas.Status.from_post(post, interactions=interactions)


@identity_required
@api_view.post
def unfavourite_status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.unlike_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return schemas.Status.from_post(post, interactions=interactions)


@api_view.get
def favourited_by(
    request: HttpRequest,
    id: str,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> ApiResponse[list[schemas.Account]]:
    """
    View who favourited a given status.
    """
    # This method should filter out private statuses, but we don't really have
    # a concept of "private status" yet.
    post = get_object_or_404(Post, pk=id)

    paginator = MastodonPaginator()
    pager: PaginationResult[PostInteraction] = paginator.paginate(
        post.interactions.filter(
            type=PostInteraction.Types.like,
            state__in=PostInteractionStates.group_active(),
        ).select_related("identity"),
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )

    headers = {}
    if pager.results:
        headers = {"link": pager.link_header(request, ["limit"])}
    return ApiResponse(
        [
            schemas.Account.from_identity(
                interaction.identity,
                include_counts=False,
            )
            for interaction in pager.results
        ],
        headers=headers,
    )


@identity_required
@api_view.post
def reblog_status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.boost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return schemas.Status.from_post(post, interactions=interactions)


@identity_required
@api_view.post
def unreblog_status(request, id: str) -> schemas.Status:
    post = get_object_or_404(Post, pk=id)
    service = PostService(post)
    service.unboost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return schemas.Status.from_post(post, interactions=interactions)
