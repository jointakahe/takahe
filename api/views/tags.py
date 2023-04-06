from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from hatchway import api_view

from activities.models import Hashtag
from api import schemas
from api.decorators import scope_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult
from users.models import HashtagFollow


@api_view.get
def hashtag(request: HttpRequest, hashtag: str) -> schemas.Tag:
    tag = get_object_or_404(
        Hashtag,
        pk=hashtag.lower(),
    )
    following = None
    if request.identity:
        following = tag.followers.filter(identity=request.identity).exists()

    return schemas.Tag.from_hashtag(
        tag,
        following=following,
    )


@scope_required("read:follows")
@api_view.get
def followed_tags(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 100,
) -> list[schemas.Tag]:
    queryset = HashtagFollow.objects.by_identity(request.identity)
    paginator = MastodonPaginator()
    pager: PaginationResult[HashtagFollow] = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    return PaginatingApiResponse(
        schemas.FollowedTag.map_from_follows(pager.results),
        request=request,
        include_params=["limit"],
    )


@scope_required("write:follows")
@api_view.post
def follow(
    request: HttpRequest,
    id: str,
) -> schemas.Tag:
    hashtag = get_object_or_404(
        Hashtag,
        pk=id.lower(),
    )
    request.identity.hashtag_follows.get_or_create(hashtag=hashtag)
    return schemas.Tag.from_hashtag(
        hashtag,
        following=True,
    )


@scope_required("write:follows")
@api_view.post
def unfollow(
    request: HttpRequest,
    id: str,
) -> schemas.Tag:
    hashtag = get_object_or_404(
        Hashtag,
        pk=id.lower(),
    )
    request.identity.hashtag_follows.filter(hashtag=hashtag).delete()
    return schemas.Tag.from_hashtag(
        hashtag,
        following=False,
    )
