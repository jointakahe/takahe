from activities.models import PostInteraction, TimelineEvent
from api import schemas
from api.decorators import identity_required
from api.pagination import MastodonPaginator
from api.views.base import api_router


@api_router.get("/v1/notifications", response=list[schemas.Notification])
@identity_required
def notifications(
    request,
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
    queryset = (
        TimelineEvent.objects.filter(
            identity=request.identity,
            type__in=[base_types[r] for r in requested_types],
        )
        .order_by("-published")
        .select_related("subject_post", "subject_post__author", "subject_identity")
    )
    paginator = MastodonPaginator(TimelineEvent)
    events = paginator.paginate(
        queryset,
        min_id=min_id,
        max_id=max_id,
        since_id=since_id,
        limit=limit,
    )
    interactions = PostInteraction.get_event_interactions(events, request.identity)
    return [
        event.to_mastodon_notification_json(interactions=interactions)
        for event in events
    ]
