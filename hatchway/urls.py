from collections.abc import Callable
from typing import Any

from django.http import HttpResponseNotAllowed


class Methods:
    """
    Allows easy multi-method dispatch to different functions
    """

    csrf_exempt = True

    def __init__(self, **callables: Callable):
        self.callables = {
            method.lower(): callable for method, callable in callables.items()
        }
        unknown_methods = set(self.callables.keys()).difference(
            {"get", "post", "patch", "put", "delete"}
        )
        if unknown_methods:
            raise ValueError(f"Cannot route methods: {unknown_methods}")

    def __call__(self, request, *args, **kwargs) -> Any:
        method = request.method.lower()
        if method in self.callables:
            return self.callables[method](request, *args, **kwargs)
        else:
            return HttpResponseNotAllowed(self.callables.keys())


methods = Methods
