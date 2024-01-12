import dataclasses

import pytest
from pytest_httpx import HTTPXMock

from core.httpy import BlockedIPError, Client  # TODO: Test async client


@dataclasses.dataclass
class MockActor:
    private_key: str
    public_key: str
    public_key_id: str


@pytest.fixture
def signing_actor(keypair):
    return MockActor(
        private_key=keypair["private_key"],
        public_key=keypair["public_key_id"],
        public_key_id="https://example.com/test-actor",
    )


def test_basics(httpx_mock: HTTPXMock):
    httpx_mock.add_response()

    with Client() as client:
        resp = client.get("https://httpbin.org/status/200")
        assert resp.status_code == 200


def test_signature_exists(httpx_mock: HTTPXMock, signing_actor):
    httpx_mock.add_response()

    with Client(actor=signing_actor) as client:
        resp = client.get("https://httpbin.org/headers")
        resp.raise_for_status()

    request = httpx_mock.get_request()
    assert request is not None
    assert "Signature" in request.headers


def test_ip_block():
    # httpx_mock actually really hates not being called, so don't use it.
    with pytest.raises(BlockedIPError), Client() as client:
        client.get("http://localhost/")
