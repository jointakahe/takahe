from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseRedirect


def moderator_required(function):
    return user_passes_test(
        lambda user: user.is_authenticated and (user.admin or user.moderator)
    )(function)


def admin_required(function):
    return user_passes_test(lambda user: user.is_authenticated and user.admin)(function)
