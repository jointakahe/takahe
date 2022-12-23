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
