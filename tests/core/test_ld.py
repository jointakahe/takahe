import datetime

from core.ld import parse_ld_date


def test_parse_ld_date():
    """
    Tests that the various kinds of LD dates that we see will work
    """
    assert parse_ld_date("2022-11-16T15:57:58Z") == datetime.datetime(
        2022,
        11,
        16,
        15,
        57,
        58,
        tzinfo=datetime.timezone.utc,
    )

    assert parse_ld_date("2022-11-16T15:57:58.123Z") == datetime.datetime(
        2022,
        11,
        16,
        15,
        57,
        58,
        tzinfo=datetime.timezone.utc,
    )
