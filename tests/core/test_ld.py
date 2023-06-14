import datetime

from dateutil.tz import tzutc

from core.ld import get_language, parse_ld_date


def test_parse_ld_date():
    """
    Tests that the various kinds of LD dates that we see will work
    """
    difference = parse_ld_date("2022-11-16T15:57:58Z") - datetime.datetime(
        2022,
        11,
        16,
        15,
        57,
        58,
        tzinfo=tzutc(),
    )
    assert difference.total_seconds() == 0

    difference = parse_ld_date("2022-11-16T15:57:58.123Z") - datetime.datetime(
        2022,
        11,
        16,
        15,
        57,
        58,
        tzinfo=tzutc(),
    )
    assert difference.total_seconds() == 0

    difference = parse_ld_date("2022-12-16T13:32:08+00:00") - datetime.datetime(
        2022,
        12,
        16,
        13,
        32,
        8,
        tzinfo=tzutc(),
    )
    assert difference.total_seconds() == 0


def test_get_language():
    assert (
        get_language(
            {
                "contentMap": {
                    "en": "<p>Hello</p>",
                    "es": "<p>hola</p>",
                },
                "nameMap": {"de": "Hallo"},
                "summaryMap": {"fr": "Bonjour"},
            }
        )
        == "en"
    )
    assert (
        get_language(
            {
                "nameMap": {"de": "Hallo"},
                "summaryMap": {"fr": "Bonjour"},
            }
        )
        == "de"
    )
    assert (
        get_language(
            {
                "summaryMap": {"fr": "Bonjour"},
            }
        )
        == "fr"
    )
    assert get_language({"contentMap": {"en-gb": "<p>Hello</p>"}}) == "en"
    assert get_language({"contentMap": {"en_GB": "<p>Hello</p>"}}) == "en"
    assert get_language({"contentMap": {"EN": "<p>Hello</p>"}}) == "en"
    assert get_language({"contentMap": {"und": "<p>Hello</p>"}}) is None
    assert get_language({}) is None
