from datetime import timedelta

from django.utils import timezone

from activities.templatetags.activity_tags import timedeltashort


def test_timedeltashort():
    """
    Tests that timedeltashort works correctly
    """
    assert timedeltashort(None) == ""
    assert timedeltashort("") == ""

    value = timezone.now()

    assert timedeltashort(value) == "0s"
    assert timedeltashort(value - timedelta(seconds=2)) == "2s"
    assert timedeltashort(value - timedelta(minutes=2)) == "2m"
    assert timedeltashort(value - timedelta(hours=2)) == "2h"
    assert timedeltashort(value - timedelta(days=2)) == "2d"
    assert timedeltashort(value - timedelta(days=364)) == "364d"
    assert timedeltashort(value - timedelta(days=365)) == "1y"
    assert timedeltashort(value - timedelta(days=366)) == "1y"

    assert timedeltashort(value + timedelta(seconds=2.1)) == "-2s"
    assert timedeltashort(value + timedelta(minutes=2, seconds=1)) == "-2m"
    assert timedeltashort(value + timedelta(hours=2, seconds=1)) == "-2h"
    assert timedeltashort(value + timedelta(days=2)) == "-2d"
    assert timedeltashort(value + timedelta(days=364)) == "-364d"
    assert timedeltashort(value + timedelta(days=365)) == "-1y"
    assert timedeltashort(value + timedelta(days=366)) == "-1y"
