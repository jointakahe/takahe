from django.http import HttpRequest
from hatchway import api_view

from api import schemas
from api.decorators import scope_required


@scope_required("read:statuses")
@api_view.get
def markers(request: HttpRequest) -> dict[str, schemas.Marker]:
    timelines = set(request.PARAMS.getlist("timeline[]"))
    data = {}
    for m in request.identity.markers.filter(timeline__in=timelines):
        data[m.timeline] = schemas.Marker.from_marker(m)
    return data


@scope_required("write:statuses")
@api_view.post
def set_markers(request: HttpRequest) -> dict[str, schemas.Marker]:
    markers = {}
    for key, last_id in request.PARAMS.items():
        if not key.endswith("[last_read_id]"):
            continue
        timeline = key.replace("[last_read_id]", "")
        marker, created = request.identity.markers.get_or_create(
            timeline=timeline,
            defaults={
                "last_read_id": last_id,
            },
        )
        if not created:
            marker.last_read_id = last_id
            marker.save()
        markers[timeline] = schemas.Marker.from_marker(marker)
    return markers
