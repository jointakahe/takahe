from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read")
@api_view.get
def suggested_users(
    request: HttpRequest,
    limit: int = 10,
    offset: int | None = None,
) -> list[schemas.Account]:
    # We don't implement this yet
    return []
