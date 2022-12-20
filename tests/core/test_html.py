from core.html import html_to_plaintext, sanitize_html


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
