from typing import Optional

from django.db import models, transaction
from django.utils import timezone


class Task(models.Model):
    """
    A task that must be done by a queue processor
    """

    class TypeChoices(models.TextChoices):
        identity_fetch = "identity_fetch"

    type = models.CharField(max_length=500, choices=TypeChoices.choices)
    priority = models.IntegerField(default=0)
    subject = models.TextField()
    payload = models.JSONField(blank=True, null=True)
    error = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(blank=True, null=True)
    failed = models.DateTimeField(blank=True, null=True)
    locked = models.DateTimeField(blank=True, null=True)
    locked_by = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"{self.id}/{self.type}({self.subject})"

    @classmethod
    def get_one_available(cls, processor_id) -> Optional["Task"]:
        """
        Gets one task off the list while reserving it, atomically.
        """
        with transaction.atomic():
            next_task = cls.objects.filter(locked__isnull=True).first()
            if next_task is None:
                return None
            next_task.locked = timezone.now()
            next_task.locked_by = processor_id
            next_task.save()
            return next_task

    @classmethod
    def submit(cls, type, subject, payload=None, deduplicate=True):
        # Deduplication is done against tasks that have not started yet only,
        # and only on tasks without payloads
        if deduplicate and not payload:
            if cls.objects.filter(
                type=type,
                subject=subject,
                completed__isnull=True,
                failed__isnull=True,
                locked__isnull=True,
            ).exists():
                return
        cls.objects.create(type=type, subject=subject, payload=payload)

    async def complete(self):
        await self.__class__.objects.filter(id=self.id).aupdate(
            completed=timezone.now()
        )

    async def fail(self, error):
        await self.__class__.objects.filter(id=self.id).aupdate(
            failed=timezone.now(),
            error=error,
        )
