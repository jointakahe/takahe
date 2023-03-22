import pytest

from core.html import FediverseHtmlParser


@pytest.mark.django_db
def test_parser(identity):
    """
    Validates the HtmlParser in its various output modes
    """

    # Basic tag allowance
    parser = FediverseHtmlParser("<p>Hello!</p><script></script>")
    assert parser.html == "<p>Hello!</p>"
    assert parser.plain_text == "Hello!"

    # Newline erasure
    parser = FediverseHtmlParser("<p>Hi!</p>\n\n<p>How are you?</p>")
    assert parser.html == "<p>Hi!</p><p>How are you?</p>"
    assert parser.plain_text == "Hi!\n\nHow are you?"

    # Trying to be evil
    parser = FediverseHtmlParser("<scri<span></span>pt>")
    assert "<scr" not in parser.html
    parser = FediverseHtmlParser("<scri #hashtag pt>")
    assert "<scr" not in parser.html

    # Entities are escaped
    parser = FediverseHtmlParser("<p>It&#39;s great</p>", find_hashtags=True)
    assert parser.html == "<p>It&#x27;s great</p>"
    assert parser.plain_text == "It's great"
    assert parser.hashtags == set()

    # Linkify works, but only with protocol prefixes
    parser = FediverseHtmlParser("<p>test.com</p>")
    assert parser.html == "<p>test.com</p>"
    assert parser.plain_text == "test.com"
    parser = FediverseHtmlParser("<p>https://test.com</p>")
    assert (
        parser.html == '<p><a href="https://test.com" rel="nofollow">test.com</a></p>'
    )
    assert parser.plain_text == "https://test.com"

    # Links are preserved
    parser = FediverseHtmlParser("<a href='https://takahe.social'>takahe social</a>")
    assert (
        parser.html
        == '<a href="https://takahe.social" rel="nofollow">takahe social</a>'
    )
    assert parser.plain_text == "https://takahe.social"

    # Very long links are shortened
    full_url = "https://social.example.com/a-long/path/that-should-be-shortened"
    parser = FediverseHtmlParser(f"<p>{full_url}</p>")
    assert (
        parser.html
        == f'<p><a href="{full_url}" rel="nofollow" class="ellipsis" title="{full_url.removeprefix("https://")}">social.example.com/a-long/path</a></p>'
    )
    assert (
        parser.plain_text
        == "https://social.example.com/a-long/path/that-should-be-shortened"
    )

    # Make sure things that look like mentions are left alone with no mentions supplied.
    parser = FediverseHtmlParser(
        "<p>@test@example.com</p>",
        find_mentions=True,
        find_hashtags=True,
        find_emojis=True,
    )
    assert parser.html == "<p>@test@example.com</p>"
    assert parser.plain_text == "@test@example.com"
    assert parser.mentions == {"test@example.com"}

    # Make sure mentions work when there is a mention supplied
    parser = FediverseHtmlParser(
        "<p>@test@example.com</p>",
        mentions=[identity],
        find_hashtags=True,
        find_emojis=True,
    )
    assert parser.html == '<p><a href="/@test@example.com/">@test</a></p>'
    assert parser.plain_text == "@test@example.com"
    assert parser.mentions == {"test@example.com"}

    # Ensure mentions are case insensitive
    parser = FediverseHtmlParser(
        "<p>@TeSt@ExamPle.com</p>",
        mentions=[identity],
        find_hashtags=True,
        find_emojis=True,
    )
    assert parser.html == '<p><a href="/@test@example.com/">@TeSt</a></p>'
    assert parser.plain_text == "@TeSt@ExamPle.com"
    assert parser.mentions == {"test@example.com"}

    # Ensure hashtags are linked, even through spans, but not within hrefs
    parser = FediverseHtmlParser(
        '<a href="http://example.com#notahashtag">something</a> <span>#</span>hashtag <a href="https://example.com/tags/hashtagtwo/">#hashtagtwo</a>',
        find_hashtags=True,
        find_emojis=True,
    )
    assert (
        parser.html
        == '<a href="http://example.com#notahashtag" rel="nofollow">something</a> <a href="/tags/hashtag/" rel="tag">#hashtag</a> <a href="/tags/hashtagtwo/" rel="tag">#hashtagtwo</a>'
    )
    assert parser.plain_text == "http://example.com#notahashtag #hashtag #hashtagtwo"
    assert parser.hashtags == {"hashtag", "hashtagtwo"}

    # Ensure lists are rendered reasonably
    parser = FediverseHtmlParser(
        "<p>List:</p><ul><li>One</li><li>Two</li><li>Three</li></ul><p>End!</p>",
        find_hashtags=True,
        find_emojis=True,
    )
    assert parser.html == "<p>List:</p><p>One<br>Two<br>Three</p><p>End!</p>"
    assert parser.plain_text == "List:\n\nOne\nTwo\nThree\n\nEnd!"


@pytest.mark.django_db
def test_parser_same_name_mentions(remote_identity, remote_identity2):
    """
    Ensure mentions that differ only by link are parsed right
    """

    parser = FediverseHtmlParser(
        '<span class="h-card"><a href="https://remote.test/@test/" class="u-url mention" rel="nofollow noreferrer noopener" target="_blank">@<span>test</span></a></span> <span class="h-card"><a href="https://remote2.test/@test/" class="u-url mention" rel="nofollow noreferrer noopener" target="_blank">@<span>test</span></a></span>',
        mentions=[remote_identity, remote_identity2],
        find_hashtags=True,
        find_emojis=True,
    )
    assert (
        parser.html
        == '<a href="/@test@remote.test/">@test</a> <a href="/@test@remote2.test/">@test</a>'
    )
    assert parser.plain_text == "@test @test"
