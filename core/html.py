import bleach
from django.utils.safestring import mark_safe


def sanitize_post(post_html: str) -> str:
    """
    Only allows a, br, p and span tags, and class attributes.
    """
    return mark_safe(
        bleach.clean(post_html, tags=["a", "br", "p", "span"], attributes=["class"])
    )
