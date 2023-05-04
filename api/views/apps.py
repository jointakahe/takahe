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
    application = Application.create(
        client_name=client_name,
        website=website,
        redirect_uris=redirect_uris,
        scopes=scopes,
    )
    return schemas.Application.from_orm(application)
