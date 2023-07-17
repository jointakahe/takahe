import pytest
from django.test.client import RequestFactory
from pytest_httpx import HTTPXMock

from core.signatures import HttpSignature
from users.models import SystemActor


@pytest.mark.django_db
def test_system_actor_signed(config_system, httpx_mock: HTTPXMock):
    """
    Tests that the system actor signs requests properly
    """
    system_actor = SystemActor()
    system_actor.generate_keys()
    # Send a fake outbound request
    httpx_mock.add_response()
    system_actor.signed_request(
        method="get",
        uri="http://example.com/test-actor",
    )
    # Retrieve it and construct a fake request object
    outbound_request = httpx_mock.get_request()
    fake_request = RequestFactory().get(
        path="/test-actor",
        HTTP_HOST="example.com",
        HTTP_DATE=outbound_request.headers["date"],
        HTTP_SIGNATURE=outbound_request.headers["signature"],
        HTTP_ACCEPT=outbound_request.headers["accept"],
    )
    # Verify that
    HttpSignature.verify_request(fake_request, system_actor.public_key)
