import re
from typing import Set

import urlman
from django.db import models

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

    hashtag_regex = re.compile(r"(?:#?)([a-zA-Z0-9(_)]{1,})")

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

    @classmethod
    def hashtags_from_content(cls, content) -> Set:
        hashtag_hits = cls.hashtag_regex.findall(content)
        hashtags = {tag.lower() for tag in hashtag_hits}
        # TODO: stemming?
        return hashtags
