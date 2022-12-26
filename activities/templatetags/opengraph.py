from django import template

register = template.Library()


@register.filter
def dict_merge(base: dict, defaults: dict):
    """
    Merges two input dictionaries, returning the merged result.

    `input|dict_merge:defaults`

    The defaults are overridden by any key present in the `input` dict.
    """
    if not (isinstance(base, dict) or isinstance(defaults, dict)):
        raise ValueError("Filter inputs must be dictionaries")

    result = {}

    result.update(defaults)
    result.update(base)

    return result
