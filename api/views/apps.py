from hatchway import QueryOrBody, api_view

from api import schemas
from api.decorators import scope_required
from api.models import Application


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
    return schemas.Application.from_application(application)


@scope_required("read")
@api_view.get
def verify_credentials(
    request,
) -> schemas.Application:
    return schemas.Application.from_application_no_keys(request.token.application)
