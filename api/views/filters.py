from hatchway import api_view

from api.decorators import identity_required


@identity_required
@api_view.get
def list_filters(request):
    return []
