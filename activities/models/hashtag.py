import re
from datetime import date, timedelta

import urlman
from asgiref.sync import sync_to_async
from django.db import models
from django.utils import timezone

from core.models import Config
from stator.models import State, StateField, StateGraph, StatorModel


class HashtagStates(StateGraph):
    outdated = State(try_interval=300, force_initial=True)
    updated = State(externally_progressed=True)

    outdated.transitions_to(updated)
    updated.transitions_to(outdated)

    @classmethod
    async def handle_outdated(cls, instance: "Hashtag"):
        """
        Computes the stats and other things for a Hashtag
        """
        from .post import Post

        posts_query = Post.objects.local_public().tagged_with(instance)
        total = await posts_query.acount()

        today = timezone.now().date()
        total_today = await posts_query.filter(
            created__gte=today,
            created__lte=today + timedelta(days=1),
        ).acount()
        total_month = await posts_query.filter(
            created__year=today.year,
            created__month=today.month,
        ).acount()
        total_year = await posts_query.filter(
            created__year=today.year,
        ).acount()
        if total:
            if not instance.stats:
                instance.stats = {}
            instance.stats.update(
                {
                    "total": total,
                    today.isoformat(): total_today,
                    today.strftime("%Y-%m"): total_month,
                    today.strftime("%Y"): total_year,
                }
            )
            instance.stats_updated = timezone.now()
            await sync_to_async(instance.save)()

        return cls.updated


class HashtagQuerySet(models.QuerySet):
    def public(self):
        public_q = models.Q(public=True)
        if Config.system.hashtag_unreviewed_are_public:
            public_q |= models.Q(public__isnull=True)
        return self.filter(public_q)

    def hashtag_or_alias(self, hashtag: str):
        return self.filter(
            models.Q(hashtag=hashtag) | models.Q(aliases__contains=hashtag)
        )


class HashtagManager(models.Manager):
    def get_queryset(self):
        return HashtagQuerySet(self.model, using=self._db)

    def public(self):
        return self.get_queryset().public()

    def hashtag_or_alias(self, hashtag: str):
        return self.get_queryset().hashtag_or_alias(hashtag)


class Hashtag(StatorModel):
    MAXIMUM_LENGTH = 100

    # Normalized hashtag without the '#'
    hashtag = models.SlugField(primary_key=True, max_length=100)

    # Friendly display override
    name_override = models.CharField(max_length=100, null=True, blank=True)

    # Should this be shown in the public UI?
    public = models.BooleanField(null=True)

    # State of this Hashtag
    state = StateField(HashtagStates)

    # Metrics for this Hashtag
    stats = models.JSONField(null=True, blank=True)
    # Timestamp of last time the stats were updated
    stats_updated = models.DateTimeField(null=True, blank=True)

    # List of other hashtags that are considered similar
    aliases = models.JSONField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = HashtagManager()

    class urls(urlman.Urls):
        view = "/tags/{self.hashtag}/"
        follow = "/tags/{self.hashtag}/follow/"
        unfollow = "/tags/{self.hashtag}/unfollow/"
        admin = "/admin/hashtags/"
        admin_edit = "{admin}{self.hashtag}/"
        admin_enable = "{admin_edit}enable/"
        admin_disable = "{admin_edit}disable/"
        timeline = "/tags/{self.hashtag}/"

    hashtag_regex = re.compile(r"\B#([a-zA-Z0-9(_)]+\b)(?!;)")

    def save(self, *args, **kwargs):
        self.hashtag = self.hashtag.lstrip("#")
        if self.name_override:
            self.name_override = self.name_override.lstrip("#")
        return super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.name_override or self.hashtag

    def __str__(self):
        return self.display_name

    def usage_months(self, num: int = 12) -> dict[date, int]:
        """
        Return the most recent num months of stats
        """
        if not self.stats:
            return {}
        results = {}
        for key, val in self.stats.items():
            parts = key.split("-")
            if len(parts) == 2:
                year = int(parts[0])
                month = int(parts[1])
                results[date(year, month, 1)] = val
        return dict(sorted(results.items(), reverse=True)[:num])

    def usage_days(self, num: int = 7) -> dict[date, int]:
        """
        Return the most recent num days of stats
        """
        if not self.stats:
            return {}
        results = {}
        for key, val in self.stats.items():
            parts = key.split("-")
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                results[date(year, month, day)] = val
        return dict(sorted(results.items(), reverse=True)[:num])

    def to_mastodon_json(self, following: bool | None = None):
        value = {
            "name": self.hashtag,
            "url": self.urls.view.full(),  # type: ignore
            "history": [],
        }

        if following is not None:
            value["following"] = following

        return value
