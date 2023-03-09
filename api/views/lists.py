from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read:lists")
@api_view.get
def get_lists(request: HttpRequest) -> list[schemas.List]:
    # We don't implement this yet
    return []
