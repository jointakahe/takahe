import json

import pytest
from pytest_httpx import HTTPXMock

from users.models import Follow, FollowStates, Identity, InboxMessage
from users.services import IdentityService


@pytest.mark.django_db
@pytest.mark.parametrize("ref_only", [True, False])
def test_follow(
    identity: Identity,
    remote_identity: Identity,
    stator,
    httpx_mock: HTTPXMock,
    ref_only: bool,
):
    """
    Ensures that follow sending and acceptance works
    """
    # Make the follow
    follow = IdentityService(identity).follow(remote_identity)
    assert Follow.objects.get(pk=follow.pk).state == FollowStates.unrequested
    # Run stator to make it try and send out the remote request
    httpx_mock.add_response(
        url="https://remote.test/@test/inbox/",
        status_code=202,
    )
    stator.run_single_cycle()
    outbound_data = json.loads(httpx_mock.get_request().content)
    assert outbound_data["type"] == "Follow"
    assert outbound_data["actor"] == identity.actor_uri
    assert outbound_data["object"] == remote_identity.actor_uri
    assert outbound_data["id"] == f"{identity.actor_uri}follow/{follow.pk}/"
    assert Follow.objects.get(pk=follow.pk).state == FollowStates.pending_approval
    # Come in with an inbox message of either a reference type or an embedded type
    if ref_only:
        message = {
            "type": "Accept",
            "id": "test",
            "actor": remote_identity.actor_uri,
            "object": outbound_data["id"],
        }
    else:
        del outbound_data["@context"]
        message = {
            "type": "Accept",
            "id": "test",
            "actor": remote_identity.actor_uri,
            "object": outbound_data,
        }
    InboxMessage.objects.create(message=message)
    # Run stator and ensure that accepted our follow
    stator.run_single_cycle()
    stator.run_single_cycle()
    assert Follow.objects.get(pk=follow.pk).state == FollowStates.accepted
