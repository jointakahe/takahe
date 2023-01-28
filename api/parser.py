import json

from ninja.parser import Parser


class FormOrJsonParser(Parser):
    """
    If there's form data in a request, makes it into a JSON dict.
    This is needed as the Mastodon API allows form data OR json body as input.
    """

    def parse_body(self, request):
        # Did they submit JSON?
        if request.content_type == "application/json" and request.body.strip():
            return json.loads(request.body)
        # Fall back to form data
        value = {}
        for key, item in request.POST.items():
            value[key] = item
        for key, item in request.GET.items():
            value[key] = item
        return value
