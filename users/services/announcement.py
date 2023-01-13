from django.db import models
from django.utils import timezone

from users.models import Announcement, User


class AnnouncementService:
    """
    Handles viewing and dismissing announcements
    """

    def __init__(self, user: User):
        self.user = user

    @classmethod
    def visible_queryset(cls) -> models.QuerySet[Announcement]:
        """
        Common visibility query
        """
        now = timezone.now()
        return Announcement.objects.filter(
            models.Q(start__lte=now) | models.Q(start__isnull=True),
            models.Q(end__gte=now) | models.Q(end__isnull=True),
            published=True,
        ).order_by("-start", "-created")

    @classmethod
    def visible_anonymous(cls) -> models.QuerySet[Announcement]:
        """
        Returns all announcements marked as being showable to all visitors
        """
        return cls.visible_queryset().filter(include_unauthenticated=True)

    def visible(self) -> models.QuerySet[Announcement]:
        """
        Returns all announcements that are currently valid and should be shown
        to a given user.
        """
        return self.visible_queryset().exclude(seen=self.user)

    def mark_seen(self, announcement: Announcement):
        """
        Marks an announcement as seen by the user
        """
        announcement.seen.add(self.user)
