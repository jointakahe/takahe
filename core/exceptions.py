import traceback

from asgiref.sync import sync_to_async
from django.conf import settings


class ActivityPubError(BaseException):
    """
    A problem with an ActivityPub message
    """


class ActorMismatchError(ActivityPubError):
    """
    The actor is not authorised to do the action we saw
    """


def capture_message(message: str):
    """
    Sends the informational message to Sentry if it's configured
    """
    if settings.SENTRY_ENABLED:
        from sentry_sdk import capture_message

        capture_message(message)
    elif settings.DEBUG:
        print(message)


def capture_exception(exception: BaseException):
    """
    Sends the exception to Sentry if it's configured
    """
    if settings.SENTRY_ENABLED:
        from sentry_sdk import capture_exception

        capture_exception(exception)
    elif settings.DEBUG:
        traceback.print_exc()


acapture_exception = sync_to_async(capture_exception, thread_sensitive=False)
