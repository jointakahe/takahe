from core.html import html_to_plaintext


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
