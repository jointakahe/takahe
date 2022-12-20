from activities.models import Hashtag
from core.html import ContentRenderer


def test_hashtag_from_content():
    assert Hashtag.hashtags_from_content("#hashtag") == ["hashtag"]
    assert Hashtag.hashtags_from_content("a#hashtag") == []
    assert Hashtag.hashtags_from_content("Text #with #hashtag in it") == [
        "hashtag",
        "with",
    ]
    assert Hashtag.hashtags_from_content("#hashtag.") == ["hashtag"]
    assert Hashtag.hashtags_from_content("More text\n#one # two ##three #hashtag!") == [
        "hashtag",
        "one",
        "three",
    ]
    assert Hashtag.hashtags_from_content("my #html loves &#32; entities") == ["html"]
    assert Hashtag.hashtags_from_content("<span class='hash'>#</span>tag") == ["tag"]


def test_linkify_hashtag():
    linkify = lambda html: ContentRenderer(local=True).linkify_hashtags(html, None)

    assert linkify("# hashtag") == "# hashtag"
    assert (
        linkify('<a href="/url/with#anchor">Text</a>')
        == '<a href="/url/with#anchor">Text</a>'
    )
    assert (
        linkify("#HashTag") == '<a class="hashtag" href="/tags/hashtag/">#HashTag</a>'
    )
    assert (
        linkify(
            """A longer text #bigContent
with #tags, linebreaks, and
maybe a few <a href="https://awesome.sauce/about#spicy">links</a>
#allTheTags #AllTheTags #ALLTHETAGS"""
        )
        == """A longer text <a class="hashtag" href="/tags/bigcontent/">#bigContent</a>
with <a class="hashtag" href="/tags/tags/">#tags</a>, linebreaks, and
maybe a few <a href="https://awesome.sauce/about#spicy">links</a>
<a class="hashtag" href="/tags/allthetags/">#allTheTags</a> <a class="hashtag" href="/tags/allthetags/">#AllTheTags</a> <a class="hashtag" href="/tags/allthetags/">#ALLTHETAGS</a>"""
    )
