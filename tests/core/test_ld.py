import datetime

from dateutil.tz import tzutc

from core.ld import canonicalise, parse_ld_date


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


def test_canonicalise_single_attachment():
    data = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            {
                "schema": "http://schema.org#",
                "PropertyValue": "schema:PropertyValue",
                "value": "schema:value",
            },
        ],
        "attachment": [
            {
                "type": "http://schema.org#PropertyValue",
                "name": "Location",
                "http://schema.org#value": "Test Location",
            },
        ],
    }

    parsed = canonicalise(data)
    attachment = parsed["attachment"]

    assert attachment["type"] == "PropertyValue"
    assert attachment["name"] == "Location"
    assert attachment["value"] == "Test Location"


def test_canonicalise_multiple_attachment():
    data = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            {
                "schema": "http://schema.org#",
                "PropertyValue": "schema:PropertyValue",
                "value": "schema:value",
            },
        ],
        "attachment": [
            {
                "type": "http://schema.org#PropertyValue",
                "name": "Attachment 1",
                "http://schema.org#value": "Test 1",
            },
            {
                "type": "http://schema.org#PropertyValue",
                "name": "Attachment 2",
                "http://schema.org#value": "Test 2",
            },
        ],
    }

    parsed = canonicalise(data)
    attachment = parsed["attachment"]

    assert len(attachment) == 2

    assert attachment[0]["type"] == "PropertyValue"
    assert attachment[0]["name"] == "Attachment 1"
    assert attachment[0]["value"] == "Test 1"

    assert attachment[1]["type"] == "PropertyValue"
    assert attachment[1]["name"] == "Attachment 2"
    assert attachment[1]["value"] == "Test 2"
