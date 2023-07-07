import traceback

from django.conf import settings


class ActivityPubError(BaseException):
    """
    A problem with an ActivityPub message
    """


class ActivityPubFormatError(ActivityPubError):
    """
    A problem with an ActivityPub message's format/keys
    """


class ActorMismatchError(ActivityPubError):
    """
    The actor is not authorised to do the action we saw
    """


def capture_message(message: str, level: str | None = None, scope=None, **scope_args):
    """
    Sends the informational message to Sentry if it's configured
    """
    if settings.SETUP.SENTRY_DSN and settings.SETUP.SENTRY_CAPTURE_MESSAGES:
        from sentry_sdk import capture_message

        capture_message(message, level, scope, **scope_args)
    elif settings.DEBUG:
        if scope or scope_args:
            message += f"; {scope=}, {scope_args=}"
        print(message)


def capture_exception(exception: BaseException, scope=None, **scope_args):
    """
    Sends the exception to Sentry if it's configured
    """
    if settings.SETUP.SENTRY_DSN:
        from sentry_sdk import capture_exception

        capture_exception(exception, scope, **scope_args)
    elif settings.DEBUG:
        traceback.print_exc()
