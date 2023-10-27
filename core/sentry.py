from contextlib import contextmanager

from django.conf import settings

SENTRY_ENABLED = False
try:
    if settings.SETUP.SENTRY_DSN:
        import sentry_sdk

        SENTRY_ENABLED = True
except ImportError:
    pass


def noop(*args, **kwargs):
    pass


@contextmanager
def noop_context(*args, **kwargs):
    yield


if SENTRY_ENABLED:
    configure_scope = sentry_sdk.configure_scope
    push_scope = sentry_sdk.push_scope
    set_context = sentry_sdk.set_context
    set_tag = sentry_sdk.set_tag
    start_transaction = sentry_sdk.start_transaction
    start_span = sentry_sdk.start_span
else:
    configure_scope = noop_context
    push_scope = noop_context
    set_context = noop
    set_tag = noop
    start_transaction = noop_context
    start_span = noop_context


def set_takahe_app(name: str):
    set_tag("takahe.app", name)


def scope_clear(scope):
    if scope:
        scope.clear()


def set_transaction_name(scope, name: str):
    if scope:
        scope.set_transaction_name(name)
