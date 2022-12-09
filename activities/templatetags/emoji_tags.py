from cachetools import TTLCache, cached
from django import template

from activities.models import Emoji
from users.models import Domain

register = template.Library()


@cached(cache=TTLCache(maxsize=1000, ttl=60))
def emoji_from_domain(domain: Domain | None) -> list[Emoji]:
    if not domain:
        return list(Emoji.locals.values())
    return list(Emoji.objects.usable(domain))


@register.filter
def imageify_emojis(value: str, arg: Domain | None = None):
    """
    Convert hashtags in content in to /tags/<hashtag>/ links.
    """
    if not value:
        return ""

    emojis = emoji_from_domain(arg)

    return Emoji.imageify_emojis(value, emojis=emojis)
