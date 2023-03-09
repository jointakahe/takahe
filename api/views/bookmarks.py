from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read:bookmarks")
@api_view.get
def bookmarks(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
) -> list[schemas.Status]:
    # We don't implement this yet
    return []
