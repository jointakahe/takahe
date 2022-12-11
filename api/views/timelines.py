from activities.models import TimelineEvent

from .. import schemas
from ..decorators import identity_required
from .base import api


@api.get("/v1/timelines/home", response=list[schemas.Status])
@identity_required
def home(request):
    if request.GET.get("max_id"):
        return []
    limit = int(request.GET.get("limit", "20"))
    events = (
        TimelineEvent.objects.filter(
            identity=request.identity,
            type__in=[TimelineEvent.Types.post],
        )
        .select_related("subject_post", "subject_post__author")
        .prefetch_related("subject_post__attachments")
        .order_by("-created")[:limit]
    )
    return [event.subject_post.to_mastodon_json() for event in events]
