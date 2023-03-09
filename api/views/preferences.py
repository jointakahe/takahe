from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read:accounts")
@api_view.get
def preferences(request: HttpRequest) -> dict:
    # Ideally this should just return Preferences; maybe hatchway needs a way to
    # indicate response models should be serialized by alias?
    return schemas.Preferences.from_identity(request.identity).dict(by_alias=True)
