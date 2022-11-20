import datetime

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def timedeltashort(value: datetime.datetime):
    """
    A more compact version of timesince
    """
    if not value:
        return ""
    # TODO: Handle things in the future properly
    delta = timezone.now() - value
    seconds = int(delta.total_seconds())
    days = delta.days
    if seconds < 60:
        text = f"{seconds:0n}s"
    elif seconds < 60 * 60:
        minutes = seconds // 60
        text = f"{minutes:0n}m"
    elif seconds < 60 * 60 * 24:
        hours = seconds // (60 * 60)
        text = f"{hours:0n}h"
    elif days < 365:
        text = f"{days:0n}d"
    else:
        years = max(days // 365.25, 1)
        text = f"{years:0n}y"
    return text
