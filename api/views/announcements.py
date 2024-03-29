from django.shortcuts import get_object_or_404
from hatchway import api_view

from api import schemas
from api.decorators import scope_required
from users.models import Announcement
from users.services import AnnouncementService


@scope_required("read:notifications")
@api_view.get
def announcement_list(request) -> list[schemas.Announcement]:
    return [
        schemas.Announcement.from_announcement(a, request.user)
        for a in AnnouncementService(request.user).visible()
    ]


@scope_required("write:notifications")
@api_view.post
def announcement_dismiss(request, pk: str):
    announcement = get_object_or_404(Announcement, pk=pk)
    AnnouncementService(request.user).mark_seen(announcement)
