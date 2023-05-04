from django.contrib.auth.decorators import user_passes_test


def moderator_required(function):
    return user_passes_test(
        lambda user: user.is_authenticated and (user.admin or user.moderator)
    )(function)


def admin_required(function):
    return user_passes_test(lambda user: user.is_authenticated and user.admin)(function)
