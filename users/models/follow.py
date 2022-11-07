from typing import Optional

from django.db import models

from miniq.models import Task


class Follow(models.Model):
    """
    When one user (the source) follows other (the target)
    """

    source = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="outbound_follows",
    )
    target = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        related_name="inbound_follows",
    )

    uri = models.CharField(blank=True, null=True, max_length=500)
    note = models.TextField(blank=True, null=True)

    requested = models.BooleanField(default=False)
    accepted = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source", "target")]

    @classmethod
    def maybe_get(cls, source, target) -> Optional["Follow"]:
        """
        Returns a follow if it exists between source and target
        """
        try:
            return Follow.objects.get(source=source, target=target)
        except Follow.DoesNotExist:
            return None

    @classmethod
    def create_local(cls, source, target):
        """
        Creates a Follow from a local Identity to the target
        (which can be local or remote).
        """
        if not source.local:
            raise ValueError("You cannot initiate follows on a remote Identity")
        try:
            follow = Follow.objects.get(source=source, target=target)
        except Follow.DoesNotExist:
            follow = Follow.objects.create(source=source, target=target, uri="")
            follow.uri = source.actor_uri + f"follow/{follow.pk}/"
            if target.local:
                follow.requested = True
                follow.accepted = True
            else:
                Task.submit("follow_request", str(follow.pk))
            follow.save()
        return follow

    def undo(self):
        """
        Undoes this follow
        """
        if not self.target.local:
            Task.submit("follow_undo", str(self.pk))
        self.delete()
