from django.http import HttpRequest
from hatchway import api_view

from activities.models import Post
from activities.services import TimelineService
from api import schemas
from api.decorators import scope_required
from api.pagination import MastodonPaginator, PaginatingApiResponse, PaginationResult


@scope_required("read:bookmarks")
@api_view.get
def bookmarks(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> list[schemas.Status]:
    queryset = TimelineService(request.identity).bookmarks()
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
