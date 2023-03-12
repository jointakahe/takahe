from django.http import HttpRequest
from hatchway import api_view

from activities.models import Hashtag
from api import schemas
from api.decorators import scope_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult


@scope_required("read:follows")
@api_view.get
def followed_tags(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 100,
) -> list[schemas.Tag]:
    queryset = Hashtag.objects.followed_by(request.identity)
    paginator = MastodonPaginator()
    # TODO: this fails due to the Hashtag model not having an `id` field
    pager: PaginationResult[Hashtag] = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    return PaginatingApiResponse(
        # TODO: add something like map_from_post to schemas.Tag
        schemas.Tag.map_from_post(pager.results, request.identity),
        request=request,
        include_params=["limit"],
    )
