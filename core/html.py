import re
from functools import partial

import bleach
import bleach.callbacks
from bleach.html5lib_shim import Filter
from bleach.linkifier import LinkifyFilter
from django.utils.safestring import mark_safe

url_regex = re.compile(
    r"""\(*  # Match any opening parentheses.
    \b(?<![@.])(?:https?://(?:(?:\w+:)?\w+@)?)  # http://
    ([\w-]+\.)+(?:[\w-]+)(?:\:[0-9]+)?(?!\.\w)\b   # xx.yy.tld(:##)?
    (?:[/?][^\s\{{\}}\|\\\^\[\]`<>"]*)?
        # /path/zz (excluding "unsafe" chars from RFC 1738,
        # except for # and ~, which happen in practice)
    """,
    re.IGNORECASE | re.VERBOSE | re.UNICODE,
)

ALLOWED_TAGS = ["br", "p", "a"]
REWRITTEN_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "pre",
    "ul",
    "ol",
    "li",
]


class MastodonStrictTagFilter(Filter):
    """
    Implements Python equivalent of Mastodon tag rewriter

    Clone of https://github.com/mastodon/mastodon/blob/main/lib/sanitize_ext/sanitize_config.rb#L55

    Broadly this replaces all REWRITTEN_TAGS with `p` except for lists where it formats it into `<br>` lists
    """

    def __iter__(self):
        li_pending_break = False
        break_token = {
            "name": "br",
            "data": {},
            "type": "StartTag",
        }

        for token in Filter.__iter__(self):
            if token.get("name") not in REWRITTEN_TAGS or token["type"] not in [
                "StartTag",
                "EndTag",
            ]:
                yield token
                continue

            if token["type"] == "StartTag":
                if token["name"] == "li":
                    if li_pending_break:
                        # Another `li` appeared, so break after the last one
                        yield break_token
                    continue
                token["name"] = "p"
            elif token["type"] == "EndTag":
                if token["name"] == "li":
                    # Track that an `li` closed so we know a break should be considered
                    li_pending_break = True
                    continue
                if token["name"] == "ul":
                    # If the last `li` happened, then don't add a break because Mastodon doesn't
                    li_pending_break = False
                token["name"] = "p"

            yield token


class UnlinkifyFilter(Filter):
    """
    Forcibly replaces link text with the href.

    This is intented to be used when stripping <a> tags to preserve the link
    location at the expense of the link text.
    """

    def __iter__(self):
        discarding_a_text = False
        for token in Filter.__iter__(self):
            if token.get("name") == "a":
                if token["type"] == "EndTag":
                    discarding_a_text = False
                    continue
                href = token["data"].get((None, "href"))

                # If <a> has an href, we use it and throw away all content
                # within the <a>...</a>. If href missing or empty, try to find
                # text within the <a>...</a>
                if href:
                    yield {"data": href, "type": "Characters"}
                    discarding_a_text = True
                    continue
            elif not discarding_a_text:
                yield token
            # else: throw away tokens until we're out of the <a>


def allow_a(tag: str, name: str, value: str):
    if name in ["href", "title", "class"]:
        return True
    elif name == "rel":
        # Only allow rel attributes with a small subset of values
        # (we're defending against, for example, rel=me)
        rel_values = value.split()
        if all(v in ["nofollow", "noopener", "noreferrer", "tag"] for v in rel_values):
            return True
    return False


def shorten_link_text(attrs, new=False):
    """
    Applies Mastodon's link shortening behavior where URL text links are
    shortened by removing the scheme and only showing the first 30 chars.

    Orig:
        <a>https://social.example.com/a-long/path/2023/01/16/that-should-be-shortened</a>

    Becomes:
        <a>social.example.com/a-long/path</a>

    """
    text = attrs.get("_text")
    if not text:
        text = attrs.get((None, "href"))
    if text and "://" in text and len(text) > 30:
        text = text.split("://", 1)[-1]
        attrs["_text"] = text[:30]
        if len(text) > 30:
            attrs[(None, "class")] = " ".join(
                filter(None, [attrs.pop((None, "class"), ""), "ellipsis"])
            )
        # Add the full URL in to title for easier user inspection
        attrs[(None, "title")] = attrs.get((None, "href"))

    return attrs


linkify_callbacks = [bleach.callbacks.nofollow, shorten_link_text]


def sanitize_html(post_html: str) -> str:
    """
    Only allows a, br, p and span tags, and class attributes.
    """
    cleaner = bleach.Cleaner(
        tags=ALLOWED_TAGS + REWRITTEN_TAGS,
        attributes={  # type:ignore
            "a": allow_a,
            "p": ["class"],
        },
        filters=[
            partial(LinkifyFilter, url_re=url_regex, callbacks=linkify_callbacks),
            MastodonStrictTagFilter,
        ],
        strip=True,
    )
    return mark_safe(cleaner.clean(post_html))


def strip_html(post_html: str, *, linkify: bool = True) -> str:
    """
    Strips all tags from the text, then linkifies it.
    """
    cleaner = bleach.Cleaner(
        tags=[],
        strip=True,
        filters=[partial(LinkifyFilter, url_re=url_regex, callbacks=linkify_callbacks)]
        if linkify
        else [UnlinkifyFilter],
    )
    return mark_safe(cleaner.clean(post_html))


def html_to_plaintext(post_html: str) -> str:
    """
    Tries to do the inverse of the linebreaks filter.
    """
    # TODO: Handle HTML entities
    # Remove all newlines, then replace br with a newline and /p with two (one comes from bleach)
    post_html = post_html.replace("\n", "").replace("<br>", "\n").replace("</p>", "\n")
    # Remove all other HTML and return
    cleaner = bleach.Cleaner(tags=["a"], strip=True, filters=[UnlinkifyFilter])
    return cleaner.clean(post_html).strip()


class ContentRenderer:
    """
    Renders HTML for posts, identity fields, and more.

    The `local` parameter affects whether links are absolute (False) or relative (True)
    """

    def __init__(self, local: bool):
        self.local = local

    def render_post(self, html: str, post) -> str:
        """
        Given post HTML, normalises it and renders it for presentation.
        """
        if not html:
            return ""
        html = sanitize_html(html)
        html = self.linkify_mentions(html, post=post)
        html = self.linkify_hashtags(html, identity=post.author)
        if self.local:
            html = self.imageify_emojis(
                html,
                identity=post.author,
                emojis=post.emojis.all(),
            )
        html = self.remove_extra_newlines(html)
        return mark_safe(html)

    def render_identity_summary(self, html: str, identity, strip: bool = False) -> str:
        """
        Given identity summary HTML, normalises it and renders it for presentation.
        """
        if not html:
            return ""
        if strip:
            html = strip_html(html)
        else:
            html = sanitize_html(html)
        html = self.linkify_hashtags(html, identity=identity)
        if self.local:
            html = self.imageify_emojis(html, identity=identity)
        html = self.remove_extra_newlines(html)
        return mark_safe(html)

    def render_identity_data(self, html: str, identity, strip: bool = False) -> str:
        """
        Given name/basic value HTML, normalises it and renders it for presentation.
        """
        if not html:
            return ""
        if strip:
            html = strip_html(html)
        else:
            html = sanitize_html(html)
        if self.local:
            html = self.imageify_emojis(html, identity=identity)
        html = self.remove_extra_newlines(html)
        return mark_safe(html)

    def linkify_mentions(self, html: str, post) -> str:
        """
        Links mentions _in the context of the post_ - as in, using the mentions
        property as the only source (as we might be doing this without other
        DB access allowed)
        """
        from activities.models import Post

        possible_matches = {}
        for mention in post.mentions.all():
            if self.local:
                url = str(mention.urls.view)
            else:
                url = mention.absolute_profile_uri()
            # Might not have fetched it (yet)
            if mention.username:
                username = mention.username.lower()
                possible_matches[username] = url
                possible_matches[f"{username}@{mention.domain_id}"] = url

        collapse_name: dict[str, str] = {}

        def replacer(match):
            precursor = match.group(1)
            handle = match.group(2)
            if "@" in handle:
                short_handle = handle.split("@", 1)[0]
            else:
                short_handle = handle
            handle_hash = handle.lower()
            short_hash = short_handle.lower()
            if handle_hash in possible_matches:
                if short_hash not in collapse_name:
                    collapse_name[short_hash] = handle_hash
                elif collapse_name.get(short_hash) != handle_hash:
                    short_handle = handle
                return f'{precursor}<a href="{possible_matches[handle_hash]}">@{short_handle}</a>'
            else:
                return match.group()

        return Post.mention_regex.sub(replacer, html)

    def linkify_hashtags(self, html, identity) -> str:
        from activities.models import Hashtag

        def replacer(attrs, new=False):
            # See if the text in this link looks like a hashtag
            if not Hashtag.hashtag_regex.match(attrs.get("_text", "")):
                return attrs
            hashtag = attrs["_text"].strip().lstrip("#")
            attrs[None, "class"] = "hashtag"
            if (None, "rel") in attrs:
                del attrs[None, "rel"]
            if self.local:
                attrs[None, "href"] = f"/tags/{hashtag.lower()}/"
            else:
                attrs[
                    None, "href"
                ] = f"https://{identity.domain.uri_domain}/tags/{hashtag.lower()}/"
            return attrs

        linker = bleach.linkifier.Linker(
            url_re=Hashtag.hashtag_regex, callbacks=[replacer]
        )
        return linker.linkify(html)

    def imageify_emojis(
        self, html: str, identity, include_local: bool = True, emojis=None
    ):
        """
        Find :emoji: in content and convert to <img>. If include_local is True,
        the local emoji will be used as a fallback for any shortcodes not defined
        by emojis.
        """
        from activities.models import Emoji

        # If precached emojis were passed, prep them
        cached_emojis = {}
        if emojis:
            for emoji in emojis:
                cached_emojis[emoji.shortcode] = emoji

        def replacer(match):
            shortcode = match.group(1).lower()
            if shortcode in cached_emojis:
                return cached_emojis[shortcode].as_html()

            emoji = Emoji.get_by_domain(shortcode, identity.domain)
            if emoji and emoji.is_usable:
                return emoji.as_html()
            elif not emoji and include_local:
                emoji = Emoji.get_by_domain(shortcode, None)
                if emoji:
                    return emoji.as_html()

            return match.group()

        return Emoji.emoji_regex.sub(replacer, html)

    def remove_extra_newlines(self, html: str) -> str:
        """
        Some clients are sensitive to extra newlines even though it's HTML
        """
        # TODO: More intelligent way to strip these?
        return html.replace("\n", "")
