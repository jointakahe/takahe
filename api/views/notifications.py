from django.http import HttpRequest, HttpResponse

from activities.models import TimelineEvent
from activities.services import TimelineService
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router


@api_router.get("/v1/notifications", response=list[schemas.Notification])
@identity_required
def notifications(
    request: HttpRequest,
    response: HttpResponse,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
    account_id: str | None = None,
):
    # Types/exclude_types use weird syntax so we have to handle them manually
    base_types = {
        "favourite": TimelineEvent.Types.liked,
        "reblog": TimelineEvent.Types.boosted,
        "mention": TimelineEvent.Types.mentioned,
        "follow": TimelineEvent.Types.followed,
    }
    requested_types = set(request.GET.getlist("types[]"))
    excluded_types = set(request.GET.getlist("exclude_types[]"))
    if not requested_types:
        requested_types = set(base_types.keys())
    requested_types.difference_update(excluded_types)
    # Use that to pull relevant events
    queryset = TimelineService(request.identity).notifications(
        [base_types[r] for r in requested_types if r in base_types]
    )
    paginator = MastodonPaginator()
    pager = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    pager.jsonify_notification_events(identity=request.identity)

    if pager.results:
        response.headers["Link"] = pager.link_header(request, ["limit", "account_id"])

    return pager.json_results
