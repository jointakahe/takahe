import re
from datetime import date, timedelta
from typing import Dict, List

import urlman
from asgiref.sync import sync_to_async
from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe

from stator.models import State, StateField, StateGraph, StatorModel


class HashtagStates(StateGraph):
    outdated = State(try_interval=300)
    updated = State(externally_progressed=True)

    outdated.transitions_to(updated)

    @classmethod
    async def handle_outdated(cls, instance: "Hashtag"):
        """
        Computes the stats and other things for a Hashtag
        """
        from .post import Post

        posts_query = Post.objects.local_public().tagged_with(instance)
        total = await posts_query.acount()

        today = timezone.now().date()
        # TODO: single query
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
            print(f"Hashtag {instance.hashtag} stats={instance.stats}")
            instance.stats_updated = timezone.now()
            await sync_to_async(instance.save)()
        else:
            print(f"Hashtag {instance.hashtag} - No Totals")
        return cls.updated


class Hashtag(StatorModel):

    # Normalized hashtag without the '#'
    hashtag = models.SlugField(primary_key=True, max_length=100)

    # Friendly display override
    name_override = models.CharField(max_length=100, null=True, blank=True)

    # Should this be shown in the public UI?
    public = models.BooleanField(default=True)

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

    class urls(urlman.Urls):
        root = "/admin/hashtags/"
        create = "/admin/hashtags/create/"
        edit = "/admin/hashtags/{self.hashtag}/"
        delete = "{edit}delete/"
        timeline = "/tags/{self.hashtag}/"

    hashtag_regex = re.compile(r"((?:\B#)([a-zA-Z0-9(_)]{1,}\b))")

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

    def usage_months(self, num: int = 12) -> Dict[date, int]:
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

    def usage_days(self, num: int = 7) -> Dict[date, int]:
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

    @classmethod
    def hashtags_from_content(cls, content) -> List[str]:
        """
        Return a parsed and sanitized of hashtags found in content without
        leading '#'.
        """
        hashtag_hits = cls.hashtag_regex.findall(content)
        hashtags = sorted({tag[1].lower() for tag in hashtag_hits})
        return list(hashtags)

    @classmethod
    def linkify_hashtags(cls, content) -> str:
        def replacer(match):
            hashtag = match.group()
            return f'<a class="hashtag" href="/tags/{hashtag.lstrip("#").lower()}/">{hashtag}</a>'

        return mark_safe(Hashtag.hashtag_regex.sub(replacer, content))
