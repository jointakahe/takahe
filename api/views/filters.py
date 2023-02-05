from api.decorators import identity_required
from hatchway import api_view


@identity_required
@api_view.get
def list_filters(request):
    return []
