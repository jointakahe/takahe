import pytest

from activities.models import Emoji


@pytest.mark.django_db
def test_emoji_ingestion(identity):
    """
    Tests that emoji ingest properly from JSON-LD
    """

    emoji1 = Emoji.by_ap_tag(
        identity.domain,
        {
            "icon": {
                "type": "Image",
                "url": "https://example.com/emoji/custom/emoji1.png",
                "mediaType": "image/png",
            },
            "id": "https://example.com/emoji/custom/emoji1.png",
            "name": ":emoji1:",
            "type": "Emoji",
            "updated": "1970-01-01T00:00:00Z",
        },
        create=True,
    )
    assert emoji1.shortcode == "emoji1"

    emoji2 = Emoji.by_ap_tag(
        identity.domain,
        {
            "icon": {
                "type": "Image",
                "url": "https://example.com/emoji/custom/emoji2.png",
                "mediaType": "image/png",
            },
            "id": "https://example.com/emoji/custom/emoji2.png",
            "nameMap": {"und": ":emoji2:"},
            "type": "Emoji",
            "updated": "1970-01-01T00:00:00Z",
        },
        create=True,
    )
    assert emoji2.shortcode == "emoji2"

    cased_emoji = Emoji.by_ap_tag(
        identity.domain,
        {
            "icon": {
                "type": "Image",
                "url": "https://example.com/emoji/custom/CasedEmoji.png",
                "mediaType": "image/png",
            },
            "id": "https://example.com/emoji/custom/CasedEmoji.png",
            "nameMap": {"und": ":CasedEmoji:"},
            "type": "Emoji",
            "updated": "1970-01-01T00:00:00Z",
        },
        create=True,
    )
    assert cased_emoji.shortcode == "CasedEmoji"


@pytest.mark.django_db
def test_emoji_without_mimetype(identity):
    """
    Tests that emoji ingest properly from JSON-LD
    """

    emoji = Emoji.by_ap_tag(
        identity.domain,
        {
            "icon": {"type": "Image", "url": "https://example.com/emoji/custom/emoji"},
            "id": "https://example.com/emoji/custom/emoji",
            "nameMap": {"und": ":emoji:"},
            "type": "Emoji",
            "updated": "1970-01-01T00:00:00Z",
        },
        create=True,
    )
    assert emoji.shortcode == "emoji"
