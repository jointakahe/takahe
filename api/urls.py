from django.urls import path

from api.views import emoji, search, statuses
from hatchway import methods

urlpatterns = [
    path("v1/statuses", statuses.post_status),
    path(
        "v1/statuses/<id>",
        methods(
            get=statuses.status,
            delete=statuses.delete_status,
        ),
    ),
    path("v1/statuses/<id>/context", statuses.status_context),
    path("v1/statuses/<id>/favourite", statuses.favourite_status),
    path("v1/statuses/<id>/unfavourite", statuses.unfavourite_status),
    path("v1/statuses/<id>/favourited_by", statuses.favourited_by),
    path("v1/statuses/<id>/reblog", statuses.reblog_status),
    path("v1/statuses/<id>/unreblog", statuses.unreblog_status),
    path("v1/custom_emojis", emoji.emojis),
    path("v2/search", search.search),
]
