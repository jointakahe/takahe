from typing import Literal

from django.forms import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Schema

from activities.models import (
    Post,
    PostAttachment,
    PostInteraction,
    PostStates,
    TimelineEvent,
)
from api import schemas
from api.views.base import api_router
from core.models import Config

from ..decorators import scope_required


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
@scope_required("write")
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
@scope_required("read")
def status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.delete("/v1/statuses/{id}", response=schemas.Status)
@scope_required("write")
def delete_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    post.transition_perform(PostStates.deleted)
    TimelineEvent.objects.filter(subject_post=post, identity=request.identity).delete()
    return post.to_mastodon_json()


@api_router.get("/v1/statuses/{id}/context", response=schemas.Context)
@scope_required("read")
def status_context(request, id: str):
    post = get_object_or_404(Post, pk=id)
    parent = post.in_reply_to_post()
    ancestors = []
    if parent:
        ancestors.append(parent)
    descendants = list(Post.objects.filter(in_reply_to=post.object_uri)[:40])
    interactions = PostInteraction.get_post_interactions(
        [post] + ancestors + descendants, request.identity
    )
    return {
        "ancestors": [p.to_mastodon_json(interactions=interactions) for p in ancestors],
        "descendants": [
            p.to_mastodon_json(interactions=interactions) for p in descendants
        ],
    }


@api_router.post("/v1/statuses/{id}/favourite", response=schemas.Status)
@scope_required("write")
def favourite_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    post.like_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.post("/v1/statuses/{id}/unfavourite", response=schemas.Status)
@scope_required("write")
def unfavourite_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    post.unlike_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.post("/v1/statuses/{id}/reblog", response=schemas.Status)
@scope_required("write")
def reblog_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    post.boost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)


@api_router.post("/v1/statuses/{id}/unreblog", response=schemas.Status)
@scope_required("write")
def unreblog_status(request, id: str):
    post = get_object_or_404(Post, pk=id)
    post.unboost_as(request.identity)
    interactions = PostInteraction.get_post_interactions([post], request.identity)
    return post.to_mastodon_json(interactions=interactions)
