from activities.models import Hashtag


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
    linkify = Hashtag.linkify_hashtags

    assert linkify("# hashtag") == "# hashtag"
    assert (
        linkify('<a href="/url/with#anchor">Text</a>')
        == '<a href="/url/with#anchor">Text</a>'
    )
    assert (
        linkify("#HashTag") == '<a href="/tags/hashtag/" class="hashtag">#HashTag</a>'
    )
    assert (
        linkify(
            """A longer text #bigContent
with #tags, linebreaks, and
maybe a few <a href="https://awesome.sauce/about#spicy">links</a>
#allTheTags #AllTheTags #ALLTHETAGS"""
        )
        == """A longer text <a href="/tags/bigcontent/" class="hashtag">#bigContent</a>
with <a href="/tags/tags/" class="hashtag">#tags</a>, linebreaks, and
maybe a few <a href="https://awesome.sauce/about#spicy">links</a>
<a href="/tags/allthetags/" class="hashtag">#allTheTags</a> <a href="/tags/allthetags/" class="hashtag">#AllTheTags</a> <a href="/tags/allthetags/" class="hashtag">#ALLTHETAGS</a>"""
    )
