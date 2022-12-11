from activities.models import TimelineEvent

from .. import schemas
from ..decorators import identity_required
from .base import api_router


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
    if limit > 40:
        limit = 40
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
    events = (
        TimelineEvent.objects.filter(
            identity=request.identity,
            type__in=[base_types[r] for r in requested_types],
        )
        .order_by("-created")
        .select_related("subject_post", "subject_post__author", "subject_identity")
    )
    if max_id:
        anchor_event = TimelineEvent.objects.get(pk=max_id)
        events = events.filter(created__lt=anchor_event.created)
    if since_id:
        anchor_event = TimelineEvent.objects.get(pk=since_id)
        events = events.filter(created__gt=anchor_event.created)
    if min_id:
        # Min ID requires LIMIT events _immediately_ newer than specified, so we
        # invert the ordering to accomodate
        anchor_event = TimelineEvent.objects.get(pk=min_id)
        events = events.filter(created__gt=anchor_event.created).order_by("created")
    return [event.to_mastodon_notification_json() for event in events[:limit]]
