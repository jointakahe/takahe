from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read")
@api_view.get
def trends_tags(
    request: HttpRequest,
    limit: int = 10,
    offset: int | None = None,
) -> list[schemas.Tag]:
    # We don't implement this yet
    return []


@scope_required("read")
@api_view.get
def trends_statuses(
    request: HttpRequest,
    limit: int = 10,
    offset: int | None = None,
) -> list[schemas.Status]:
    # We don't implement this yet
    return []


@scope_required("read")
@api_view.get
def trends_links(
    request: HttpRequest,
    limit: int = 10,
    offset: int | None = None,
) -> list:
    # We don't implement this yet
    return []
