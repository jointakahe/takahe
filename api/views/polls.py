from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from activities.models import Post, PostInteraction
from api import schemas
from api.decorators import identity_required
from hatchway import Schema, api_view


class PostVoteSchema(Schema):
    choices: list[int]


@identity_required
@api_view.get
def get_poll(request, id: str) -> schemas.Poll:
    post = get_object_or_404(Post, pk=id, type=Post.Types.question)
    return schemas.Poll.from_post(post, identity=request.identity)


@identity_required
@api_view.post
def vote_poll(request, id: str, details: PostVoteSchema) -> schemas.Poll:
    post = get_object_or_404(Post, pk=id, type=Post.Types.question)
    question = post.type_data

    if question.end_time and timezone.now() > question.end_time:
        raise ValueError("Validation failed: The poll has already ended")

    if post.interactions.filter(
        identity=request.identity, type=PostInteraction.Types.vote
    ).exists():
        raise ValueError("Validation failed: You have already voted on this poll")

    with transaction.atomic():
        for choice in set(details.choices):
            PostInteraction.objects.create(
                identity=request.identity,
                post=post,
                type=PostInteraction.Types.vote,
                answer=question.options[choice].name,
            )

        post.calculate_type_data()

    post.refresh_from_db()

    return schemas.Poll.from_post(post, identity=request.identity)
