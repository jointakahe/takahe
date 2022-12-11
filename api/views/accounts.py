from .. import schemas
from ..decorators import identity_required
from .base import api


@api.get("/v1/accounts/verify_credentials", response=schemas.Account)
@identity_required
def verify_credentials(request):
    return request.identity.to_mastodon_json()
