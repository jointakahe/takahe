from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read:follows")
@api_view.get
def follow_requests(
    request: HttpRequest,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 40,
) -> list[schemas.Account]:
    # We don't implement this yet
    return []
