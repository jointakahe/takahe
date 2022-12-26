import bleach
from bleach.linkifier import LinkifyFilter
from django.utils.safestring import mark_safe


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


def sanitize_post(post_html: str) -> str:
    """
    Only allows a, br, p and span tags, and class attributes.
    """
    cleaner = bleach.Cleaner(
        tags=["br", "p", "a"],
        attributes={  # type:ignore
            "a": allow_a,
            "p": ["class"],
            "span": ["class"],
        },
        filters=[LinkifyFilter],
        strip=True,
    )
    return mark_safe(cleaner.clean(post_html))


def strip_html(post_html: str) -> str:
    """
    Strips all tags from the text, then linkifies it.
    """
    cleaner = bleach.Cleaner(tags=[], strip=True, filters=[LinkifyFilter])
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
