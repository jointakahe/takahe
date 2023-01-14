from django.shortcuts import get_object_or_404

from api import schemas
from api.decorators import identity_required
from api.views.base import api_router
from users.models import Announcement
from users.services import AnnouncementService


@api_router.get("/v1/announcements", response=list[schemas.Announcement])
@identity_required
def announcement_list(request):
    return [
        a.to_mastodon_json(request.user)
        for a in AnnouncementService(request.user).visible()
    ]


@api_router.post("/v1/announcements/{pk}/dismiss")
@identity_required
def announcement_dismiss(request, pk: str):
    announcement = get_object_or_404(Announcement, pk=pk)
    AnnouncementService(request.user).mark_seen(announcement)
