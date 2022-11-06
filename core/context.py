from django.conf import settings


def config_context(request):
    return {
        "config": {"site_name": settings.SITE_NAME},
    }
