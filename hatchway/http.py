import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse


class ApiResponse(HttpResponse):
    """
    A way to return extra information with a response if you want
    headers, etc.
    """

    def __init__(
        self,
        data: Any,
        encoder=DjangoJSONEncoder,
        json_dumps_params: dict[str, object] | None = None,
        **kwargs
    ):
        self.data = data
        self.encoder = encoder
        self.json_dumps_params = json_dumps_params or {}
        kwargs.setdefault("content_type", "application/json")
        super().__init__(content=b"(unfinalised)", **kwargs)

    def finalize(self):
        """
        Converts whatever our current data is into HttpResponse content
        """
        # TODO: Automatically call this when we're asked to write output?
        self.content = json.dumps(self.data, cls=self.encoder, **self.json_dumps_params)
