from api.decorators import identity_required
from api.views.base import api_router


@api_router.get("/v1/filters")
@identity_required
def status(request):
    return []
