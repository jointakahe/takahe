import html
import re
from html.parser import HTMLParser

from django.utils.safestring import mark_safe


class FediverseHtmlParser(HTMLParser):
    """
    A custom HTML parser that only allows a certain tag subset and behaviour:
    - br, p tags are passed through
    - a tags are passed through if they're not hashtags or mentions
    - Another set of tags are converted to p

    It also linkifies URLs, mentions, hashtags, and imagifies emoji.
    """

    REWRITE_TO_P = [
        "p",
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
    ]

    REWRITE_TO_BR = [
        "br",
        "li",
    ]

    MENTION_REGEX = re.compile(
        r"(^|[^\w\d\-_/])@([\w\d\-_]+(?:@[\w\d\-_\.]+[\w\d\-_]+)?)"
    )

    HASHTAG_REGEX = re.compile(r"\B#([a-zA-Z0-9(_)]+\b)(?!;)")

    EMOJI_REGEX = re.compile(r"\B:([a-zA-Z0-9(_)-]+):\B")

    URL_REGEX = re.compile(
        r"""(\(*  # Match any opening parentheses.
        \b(?<![@.])(?:https?://(?:(?:\w+:)?\w+@)?)  # http://
        (?:[\w-]+\.)+(?:[\w-]+)(?:\:[0-9]+)?(?!\.\w)\b   # xx.yy.tld(:##)?
        (?:[/?][^\s\{{\}}\|\\\^\[\]`<>"]*)?)
        # /path/zz (excluding "unsafe" chars from RFC 1738,
        # except for # and ~, which happen in practice)
        """,
        re.IGNORECASE | re.VERBOSE | re.UNICODE,
    )

    def __init__(
        self,
        html: str,
        uri_domain: str | None = None,
        mentions: list | None = None,
        find_mentions: bool = False,
        find_hashtags: bool = False,
        find_emojis: bool = False,
        emoji_domain=None,
    ):
        super().__init__()
        self.uri_domain = uri_domain
        self.emoji_domain = emoji_domain
        self.find_mentions = find_mentions
        self.find_hashtags = find_hashtags
        self.find_emojis = find_emojis
        self.calculate_mentions(mentions)
        self._data_buffer = ""
        self.html_output = ""
        self.text_output = ""
        self.emojis: set[str] = set()
        self.mentions: set[str] = set()
        self.hashtags: set[str] = set()
        self._pending_a: dict | None = None
        self._fresh_p = False
        self.feed(html.replace("\n", ""))
        self.flush_data()

    def calculate_mentions(self, mentions: list | None):
        """
        Prepares a set of content that we expect to see mentions look like
        (this imp)
        """
        self.mention_matches: dict[str, str] = {}
        self.mention_aliases: dict[str, str] = {}
        for mention in mentions or []:
            if self.uri_domain:
                url = mention.absolute_profile_uri()
            else:
                url = str(mention.urls.view)
            if mention.username:
                username = mention.username.lower()
                domain = mention.domain_id.lower()
                self.mention_matches[f"{username}"] = url
                self.mention_matches[f"{username}@{domain}"] = url
                self.mention_matches[mention.absolute_profile_uri()] = url

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.REWRITE_TO_P:
            self.flush_data()
            self.html_output += "<p>"
        elif tag in self.REWRITE_TO_BR:
            self.flush_data()
            if not self._fresh_p:
                self.html_output += "<br>"
                self.text_output += "\n"
        elif tag == "a":
            self.flush_data()
            self._pending_a = {"attrs": dict(attrs), "content": ""}
        self._fresh_p = tag in self.REWRITE_TO_P

    def handle_endtag(self, tag: str) -> None:
        self._fresh_p = False
        if tag in self.REWRITE_TO_P:
            self.flush_data()
            self.html_output += "</p>"
            self.text_output += "\n\n"
        elif tag == "a":
            if self._pending_a:
                href = self._pending_a["attrs"].get("href")
                content = self._pending_a["content"].strip()
                has_ellipsis = "ellipsis" in self._pending_a["attrs"].get("class", "")
                # Is it a mention?
                if content.lower().lstrip("@") in self.mention_matches:
                    self.html_output += self.create_mention(content, href)
                    self.text_output += content
                # Is it a hashtag?
                elif self.HASHTAG_REGEX.match(content):
                    self.html_output += self.create_hashtag(content)
                    self.text_output += content
                elif content:
                    # Shorten the link if we need to
                    self.html_output += self.create_link(
                        href,
                        content,
                        has_ellipsis=has_ellipsis,
                    )
                    self.text_output += href
                self._pending_a = None

    def handle_data(self, data: str) -> None:
        self._fresh_p = False
        if self._pending_a:
            self._pending_a["content"] += data
        else:
            self._data_buffer += data

    def flush_data(self) -> None:
        """
        We collect data segments until we encounter a tag we care about,
        so we can treat <span>#</span>hashtag as #hashtag
        """
        self.text_output += self._data_buffer
        self.html_output += self.linkify(self._data_buffer)
        self._data_buffer = ""

    def create_link(self, href, content, has_ellipsis=False):
        """
        Generates a link, doing optional shortening.

        All return values from this function should be HTML-safe.
        """
        looks_like_link = bool(self.URL_REGEX.match(content))
        if looks_like_link:
            content = content.split("://", 1)[1]
        if (looks_like_link and len(content) > 30) or has_ellipsis:
            return f'<a href="{html.escape(href)}" rel="nofollow" class="ellipsis" title="{html.escape(content)}">{html.escape(content[:30])}</a>'
        else:
            return f'<a href="{html.escape(href)}" rel="nofollow">{html.escape(content)}</a>'

    def create_mention(self, handle, href: str | None = None) -> str:
        """
        Generates a mention link. Handle should have a leading @.

        All return values from this function should be HTML-safe
        """
        handle = handle.lstrip("@")
        if "@" in handle:
            short_handle = handle.split("@", 1)[0]
        else:
            short_handle = handle
        handle_hash = handle.lower()
        short_hash = short_handle.lower()
        self.mentions.add(handle_hash)
        url = self.mention_matches.get(handle_hash)
        # If we have a captured link out, use that as the actual resolver
        if href and href in self.mention_matches:
            url = self.mention_matches[href]
        if url:
            if short_hash not in self.mention_aliases:
                self.mention_aliases[short_hash] = handle_hash
            elif self.mention_aliases.get(short_hash) != handle_hash:
                short_handle = handle
            return f'<span class="h-card"><a href="{html.escape(url)}" class="u-url mention" rel="nofollow noopener noreferrer" target="_blank">@<span>{html.escape(short_handle)}</span></a></span>'
        else:
            return "@" + html.escape(handle)

    def create_hashtag(self, hashtag) -> str:
        """
        Generates a hashtag link. Hashtag does not need to start with #

        All return values from this function should be HTML-safe
        """
        hashtag = hashtag.lstrip("#")
        self.hashtags.add(hashtag.lower())
        if self.uri_domain:
            return f'<a href="https://{self.uri_domain}/tags/{hashtag.lower()}/" class="mention hashtag" rel="tag">#{hashtag}</a>'
        else:
            return f'<a href="/tags/{hashtag.lower()}/" rel="tag">#{hashtag}</a>'

    def create_emoji(self, shortcode) -> str:
        """
        Generates an emoji <img> tag

        All return values from this function should be HTML-safe
        """
        from activities.models import Emoji

        emoji = Emoji.get_by_domain(shortcode, self.emoji_domain)
        if emoji and emoji.is_usable:
            self.emojis.add(shortcode)
            return emoji.as_html()
        return f":{shortcode}:"

    def linkify(self, data):
        """
        Linkifies some content that is plaintext.

        Handles URLs first, then mentions. Note that this takes great care to
        keep track of what is HTML and what needs to be escaped.
        """
        # Split the string by the URL regex so we know what to escape and what
        # not to escape.
        bits = self.URL_REGEX.split(data)
        result = ""
        # Even indices are data we should pass though, odd indices are links
        for i, bit in enumerate(bits):
            # A link!
            if i % 2 == 1:
                result += self.create_link(bit, bit)
            # Not a link
            elif self.mention_matches or self.find_mentions:
                result += self.linkify_mentions(bit)
            elif self.find_hashtags:
                result += self.linkify_hashtags(bit)
            elif self.find_emojis:
                result += self.linkify_emoji(bit)
            else:
                result += html.escape(bit)
        return result

    def linkify_mentions(self, data):
        """
        Linkifies mentions
        """
        bits = self.MENTION_REGEX.split(data)
        result = ""
        for i, bit in enumerate(bits):
            # Mention content
            if i % 3 == 2:
                result += self.create_mention(bit)
            # Not part of a mention (0) or mention preamble (1)
            elif self.find_hashtags:
                result += self.linkify_hashtags(bit)
            elif self.find_emojis:
                result += self.linkify_emoji(bit)
            else:
                result += html.escape(bit)
        return result

    def linkify_hashtags(self, data):
        """
        Linkifies hashtags
        """
        bits = self.HASHTAG_REGEX.split(data)
        result = ""
        for i, bit in enumerate(bits):
            # Not part of a hashtag
            if i % 2 == 0:
                if self.find_emojis:
                    result += self.linkify_emoji(bit)
                else:
                    result += html.escape(bit)
            # Hashtag content
            else:
                result += self.create_hashtag(bit)
        return result

    def linkify_emoji(self, data):
        """
        Linkifies emoji
        """
        bits = self.EMOJI_REGEX.split(data)
        result = ""
        for i, bit in enumerate(bits):
            # Not part of an emoji
            if i % 2 == 0:
                result += html.escape(bit)
            # Emoji content
            else:
                result += self.create_emoji(bit)
        return result

    @property
    def html(self):
        return self.html_output.strip()

    @property
    def plain_text(self):
        return self.text_output.strip()


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
        parser = FediverseHtmlParser(
            html,
            mentions=post.mentions.all(),
            uri_domain=(None if self.local else post.author.domain.uri_domain),
            find_hashtags=True,
            find_emojis=self.local,
            emoji_domain=post.author.domain,
        )
        return mark_safe(parser.html)

    def render_identity_summary(self, html: str, identity) -> str:
        """
        Given identity summary HTML, normalises it and renders it for presentation.
        """
        if not html:
            return ""
        parser = FediverseHtmlParser(
            html,
            uri_domain=(None if self.local else identity.domain.uri_domain),
            find_hashtags=True,
            find_emojis=self.local,
            emoji_domain=identity.domain,
        )
        return mark_safe(parser.html)

    def render_identity_data(self, html: str, identity, strip: bool = False) -> str:
        """
        Given name/basic value HTML, normalises it and renders it for presentation.
        """
        if not html:
            return ""
        parser = FediverseHtmlParser(
            html,
            uri_domain=(None if self.local else identity.domain.uri_domain),
            find_hashtags=False,
            find_emojis=self.local,
            emoji_domain=identity.domain,
        )
        if strip:
            return mark_safe(parser.html)
        else:
            return mark_safe(parser.html)
