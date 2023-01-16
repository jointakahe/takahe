from unittest.mock import Mock

import pytest

from core.html import ContentRenderer, html_to_plaintext, sanitize_html


def test_html_to_plaintext():

    assert html_to_plaintext("<p>Hi!</p>") == "Hi!"
    assert html_to_plaintext("<p>Hi!<br>There</p>") == "Hi!\nThere"
    assert (
        html_to_plaintext("<p>Hi!</p>\n\n<p>How are you?</p>") == "Hi!\n\nHow are you?"
    )

    assert (
        html_to_plaintext("<p>Hi!</p>\n\n<p>How are<br> you?</p><p>today</p>")
        == "Hi!\n\nHow are\n you?\n\ntoday"
    )


def test_sanitize_post():

    assert sanitize_html("<p>Hello!</p>") == "<p>Hello!</p>"
    assert sanitize_html("<p>It&#39;s great</p>") == "<p>It&#39;s great</p>"

    # Note that we only want to linkify things with protocol prefixes to prevent
    # too many false positives.
    assert sanitize_html("<p>test.com</p>") == "<p>test.com</p>"
    assert (
        sanitize_html("<p>https://test.com</p>")
        == '<p><a href="https://test.com" rel="nofollow">https://test.com</a></p>'
    )
    assert (
        sanitize_html("<p>@someone@subdomain.some-domain.com</p>")
        == "<p>@someone@subdomain.some-domain.com</p>"
    )


def test_shorten_url():
    full_url = (
        "https://social.example.com/a-long/path/2023/01/16/that-should-be-shortened"
    )
    assert (
        sanitize_html(f"<p>{full_url}</p>")
        == f'<p><a href="{full_url}" rel="nofollow" class="ellipsis" title="{full_url}">social.example.com/a-long/path</a></p>'
    )

    assert (
        sanitize_html(
            f'<p><a href="{full_url}">This is a long link text, but cannot be shortened as a URL</a></p>'
        )
        == f'<p><a href="{full_url}" rel="nofollow">This is a long link text, but cannot be shortened as a URL</a></p>'
    )


@pytest.mark.django_db
def test_link_preservation():
    """
    We want to:
     - Preserve incoming links from other servers
     - Linkify mentions and hashtags
     - Not have these all step on each other!
    """
    renderer = ContentRenderer(local=True)
    fake_mention = Mock()
    fake_mention.username = "andrew"
    fake_mention.domain_id = "aeracode.org"
    fake_mention.urls.view = "/@andrew@aeracode.org/"
    fake_post = Mock()
    fake_post.mentions.all.return_value = [fake_mention]
    fake_post.author.domain.uri_domain = "example.com"
    fake_post.emojis.all.return_value = []

    assert (
        renderer.render_post(
            'Hello @andrew, I want to link to this <span>#</span>hashtag: <a href="http://example.com/@andrew/#notahashtag">here</a> and rewrite <a href="https://example.com/tags/thishashtag/">#thishashtag</a>',
            fake_post,
        )
        == 'Hello <a href="/@andrew@aeracode.org/">@andrew</a>, I want to link to this <a href="/tags/hashtag/" class="hashtag">#hashtag</a>: <a href="http://example.com/@andrew/#notahashtag" rel="nofollow">here</a> and rewrite <a href="/tags/thishashtag/" class="hashtag">#thishashtag</a>'
    )


@pytest.mark.django_db
def test_list_rendering():
    """
    We want to:
     - Preserve incoming links from other servers
     - Linkify mentions and hashtags
     - Not have these all step on each other!
    """
    renderer = ContentRenderer(local=True)
    fake_mention = Mock()
    fake_mention.username = "andrew"
    fake_mention.domain_id = "aeracode.org"
    fake_mention.urls.view = "/@andrew@aeracode.org/"
    fake_post = Mock()
    fake_post.mentions.all.return_value = [fake_mention]
    fake_post.author.domain.uri_domain = "example.com"
    fake_post.emojis.all.return_value = []

    assert (
        renderer.render_post(
            "<p>Ok. The roster so far is:</p><ul><li>Infosec.exchange (mastodon)</li><li>pixel.Infosec.exchange (pixelfed)</li><li>video.Infosec.exchange (peertube)</li><li>relay.Infosec.exchange (activitypub relay)</li><li>risky.af (alt mastodon)</li></ul><p>What’s next?  I think I promised some people here bookwyrm</p>",
            fake_post,
        )
        == "<p>Ok. The roster so far is:</p><p>Infosec.exchange (mastodon)<br>pixel.Infosec.exchange (pixelfed)<br>video.Infosec.exchange (peertube)<br>relay.Infosec.exchange (activitypub relay)<br>risky.af (alt mastodon)</p><p>What’s next?  I think I promised some people here bookwyrm</p>"
    )


@pytest.mark.django_db
def test_link_mixcase_mentions():
    renderer = ContentRenderer(local=True)
    fake_mention = Mock()
    fake_mention.username = "Manfre"
    fake_mention.domain_id = "manfre.net"
    fake_mention.urls.view = "/@Manfre@manfre.net/"
    fake_mention2 = Mock()
    fake_mention2.username = "manfre"
    fake_mention2.domain_id = "takahe.social"
    fake_mention2.urls.view = "https://takahe.social/@manfre@takahe.social/"

    unfetched_mention = Mock()
    unfetched_mention.username = None
    unfetched_mention.domain_id = None
    unfetched_mention.urls.view = "/None@None/"

    fake_post = Mock()
    fake_post.mentions.all.return_value = [
        fake_mention,
        fake_mention2,
        unfetched_mention,
    ]
    fake_post.author.domain.uri_domain = "example.com"
    fake_post.emojis.all.return_value = []

    assert renderer.render_post(
        "@Manfre@manfre.net @mAnFrE@takahe.social @manfre@manfre.net @unfetched@manfre.net",
        fake_post,
    ) == (
        '<a href="/@Manfre@manfre.net/">@Manfre</a> '
        '<a href="https://takahe.social/@manfre@takahe.social/">@mAnFrE@takahe.social</a> '
        '<a href="/@Manfre@manfre.net/">@manfre</a> '
        "@unfetched@manfre.net"
    )
