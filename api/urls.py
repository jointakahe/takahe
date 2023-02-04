from django.urls import path

from api.views import statuses
from hatchway import methods

urlpatterns = [
    path(
        "v1/statuses",
        methods(
            post=statuses.post_status,
        ),
    ),
    path(
        "v1/statuses/<id>",
        methods(
            get=statuses.status,
            delete=statuses.delete_status,
        ),
    ),
]
