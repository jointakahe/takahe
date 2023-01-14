from users.services import AnnouncementService


def user_context(request):
    return {
        "announcements": (
            AnnouncementService(request.user).visible()
            if request.user.is_authenticated
            else AnnouncementService.visible_anonymous()
        )
    }
