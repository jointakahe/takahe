from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import View

from users.decorators import identity_required
from users.models import Announcement
from users.services import AnnouncementService


@method_decorator(identity_required, name="dispatch")
class AnnouncementDismiss(View):
    """
    Dismisses an announcement for the current user
    """

    def post(self, request, id):
        announcement = get_object_or_404(Announcement, pk=id)
        AnnouncementService(request.user).mark_seen(announcement)
        # In the UI we replace it with nothing anyway
        return HttpResponse("")
