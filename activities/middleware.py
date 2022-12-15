from time import time

from activities.models import Emoji


class EmojiDefaultsLoadingMiddleware:
    """
    Caches the default Emoji
    """

    refresh_interval: float = 30.0

    def __init__(self, get_response):
        self.get_response = get_response
        self.loaded_ts: float = 0.0

    def __call__(self, request):
        # Allow test fixtures to force and lock the Emojis
        if not getattr(Emoji, "__forced__", False):
            if (
                not getattr(Emoji, "locals", None)
                or (time() - self.loaded_ts) >= self.refresh_interval
            ):
                Emoji.locals = Emoji.load_locals()
                self.loaded_ts = time()
        response = self.get_response(request)
        return response
