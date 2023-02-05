import secrets

from hatchway import Schema, api_view

from .. import schemas
from ..models import Application


class CreateApplicationSchema(Schema):
    client_name: str
    redirect_uris: str
    scopes: None | str = None
    website: None | str = None


@api_view.post
def add_app(request, details: CreateApplicationSchema) -> schemas.Application:
    client_id = "tk-" + secrets.token_urlsafe(16)
    client_secret = secrets.token_urlsafe(40)
    application = Application.objects.create(
        name=details.client_name,
        website=details.website,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uris=details.redirect_uris,
        scopes=details.scopes or "read",
    )
    return schemas.Application.from_orm(application)
