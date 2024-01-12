# FIXME: Better way than hitting live httpbin?
import dataclasses

import pytest

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


def test_basics():
    with Client() as client:
        resp = client.get("https://httpbin.org/status/200")
        assert resp.status_code == 200


def test_signature_exists(signing_actor):
    with Client(actor=signing_actor) as client:
        resp = client.get("https://httpbin.org/headers")
        resp.raise_for_status()
        body = resp.json()
        assert "Signature" in body["headers"]


def test_ip_block():
    with pytest.raises(BlockedIPError), Client() as client:
        client.get("http://localhost/")
