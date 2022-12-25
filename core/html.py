import re
from functools import partial

import bleach
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


def sanitize_html(post_html: str) -> str:
    """
    Only allows a, br, p and span tags, and class attributes.
    """
    cleaner = bleach.Cleaner(
        tags=["br", "p", "a"],
        attributes={  # type:ignore
            "a": allow_a,
            "p": ["class"],
        },
        filters=[partial(LinkifyFilter, url_re=url_regex)],
        strip=True,
    )
    return mark_safe(cleaner.clean(post_html))


def strip_html(post_html: str) -> str:
    """
    Strips all tags from the text, then linkifies it.
    """
    cleaner = bleach.Cleaner(
        tags=[],
        strip=True,
        filters=[partial(LinkifyFilter, url_re=url_regex)],
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
    cleaner = bleach.Cleaner(tags=[], strip=True, filters=[])
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
            try:
                emoji = Emoji.get_by_domain(shortcode, identity.domain)
                if emoji.is_usable:
                    return emoji.as_html()
            except Emoji.DoesNotExist:
                if include_local:
                    try:
                        return Emoji.get_by_domain(shortcode, identity.domain).as_html()
                    except Emoji.DoesNotExist:
                        pass
            return match.group()

        return Emoji.emoji_regex.sub(replacer, html)
