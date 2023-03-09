import secrets

from hatchway import QueryOrBody, api_view

from .. import schemas
from ..models import Application


@api_view.post
def add_app(
    request,
    client_name: QueryOrBody[str],
    redirect_uris: QueryOrBody[str],
    scopes: QueryOrBody[None | str] = None,
    website: QueryOrBody[None | str] = None,
) -> schemas.Application:
    client_id = "tk-" + secrets.token_urlsafe(16)
    client_secret = secrets.token_urlsafe(40)
    application = Application.objects.create(
        name=client_name,
        website=website,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uris=redirect_uris,
        scopes=scopes or "read",
    )
    return schemas.Application.from_orm(application)
