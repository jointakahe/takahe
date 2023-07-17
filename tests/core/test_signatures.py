import pytest
from django.test.client import RequestFactory
from pytest_httpx import HTTPXMock

from core.signatures import HttpSignature, LDSignature, VerificationError


def test_sign_ld(keypair):
    """
    Tests signing JSON-LD documents by round-tripping them through the
    verifier.
    """
    # Create the signature
    document = {
        "id": "https://example.com/test-create",
        "type": "Create",
        "actor": "https://example.com/test-actor",
        "object": {
            "id": "https://example.com/test-object",
            "type": "Note",
        },
    }
    signature_section = LDSignature.create_signature(
        document,
        keypair["private_key"],
        keypair["public_key_id"],
    )
    # Check it and assign it to the document
    assert "signatureValue" in signature_section
    assert signature_section["type"] == "RsaSignature2017"
    document["signature"] = signature_section
    # Now verify it ourselves
    LDSignature.verify_signature(document, keypair["public_key"])


def test_verifying_ld(keypair):
    """
    Tests verifying JSON-LD signatures from a known-good document
    """
    document = {
        "id": "https://example.com/test-create",
        "type": "Create",
        "actor": "https://example.com/test-actor",
        "object": {"id": "https://example.com/test-object", "type": "Note"},
        "signature": {
            "@context": "https://w3id.org/identity/v1",
            "creator": "https://example.com/test-actor#test-key",
            "created": "2022-11-12T21:41:47Z",
            "signatureValue": "nTHfkHqG4hegfnjpHucXtXDLDaIKi2Duk+NeCzqTtkjf4NneXsofbZY2tGew4uAooEe1UeM23PIyjWYnR16KwcD4YY8nMj8L3xY2czwQPScMM9n+KhSHzkWfX+iI4FWKbjpPI8M53EtTRJU+1qEjjmGUx03Ip0vfvT5821etIgvY4wLNhg3y7R8fevnNux+BeytcEV6gM4awJJ6RK0xrWGLyTgDNon5V5aNUjwcV/UVPy9UAQi1KYWtA74/F0Y4oPzL5CTudPpyiViyVHZQaal4r+ExzgSvGztqKxQeT1ya6gLXxbm1YQ+8UiGVSS8zoGhMFDEZWVsRPv7e0jm5wfA==",
            "type": "RsaSignature2017",
        },
    }
    # Ensure it verifies with correct data
    LDSignature.verify_signature(document, keypair["public_key"])
    # Mutate it slightly and ensure it does not verify
    with pytest.raises(VerificationError):
        document["actor"] = "https://example.com/evil-actor"
        LDSignature.verify_signature(document, keypair["public_key"])


def test_sign_http(httpx_mock: HTTPXMock, keypair):
    """
    Tests signing HTTP requests by round-tripping them through our verifier
    """
    # Create document
    document = {
        "id": "https://example.com/test-create",
        "type": "Create",
        "actor": "https://example.com/test-actor",
        "object": {
            "id": "https://example.com/test-object",
            "type": "Note",
        },
    }
    # Send the signed request to the mock library
    httpx_mock.add_response()
    HttpSignature.signed_request(
        uri="https://example.com/test-actor",
        body=document,
        private_key=keypair["private_key"],
        key_id=keypair["public_key_id"],
    )
    # Retrieve it and construct a fake request object
    outbound_request = httpx_mock.get_request()
    fake_request = RequestFactory().post(
        path="/test-actor",
        data=outbound_request.content,
        content_type=outbound_request.headers["content-type"],
        HTTP_HOST="example.com",
        HTTP_DATE=outbound_request.headers["date"],
        HTTP_SIGNATURE=outbound_request.headers["signature"],
        HTTP_DIGEST=outbound_request.headers["digest"],
    )
    # Verify that
    HttpSignature.verify_request(fake_request, keypair["public_key"])


def test_verify_http(keypair):
    """
    Tests verifying HTTP requests against a known good example
    """
    # Make our predictable request
    fake_request = RequestFactory().post(
        path="/test-actor",
        data=b'{"id": "https://example.com/test-create", "type": "Create", "actor": "https://example.com/test-actor", "object": {"id": "https://example.com/test-object", "type": "Note"}}',
        content_type="application/json",
        HTTP_HOST="example.com",
        HTTP_DATE="Sat, 12 Nov 2022 21:57:18 GMT",
        HTTP_SIGNATURE='keyId="https://example.com/test-actor#test-key",headers="(request-target) host date digest content-type",signature="IRduYoDJIh90mprjUgOIdxY1iaBWHs5ou9vsDlcmSekg6DXMZTiXjmZxbNIrnpEbNFu3wTcqz1nv9H97Gp7orbYMuHm6j2ecxsvzSr37T9jxBbt3Ov3xSfuYWwhv6PuTWNxHtUQWNuAIc3wHDAQt8Flnak/uHe7swoAq4uHq2kt18iMW6CEV9XA5ESFho2HSUgRaifoNxJlIWbHYPJiP0t9aktgGBkpQoZ8ulOj3Ew4RwC1lwk9kzWiLIjU4tSAie8RbIy2g0aUvA1tQh9Uge1by3o7+349SL5iooj+B6WSCEvvjEl52wo3xoEQmv0ptYuSPLUgB9tP8q7DoHEc8Dw==",algorithm="rsa-sha256"',
        HTTP_DIGEST="SHA-256=07sIbQ3GlOHWMbFMNajtPNtmUQXXu20UuvrIYLlI3kc=",
    )
    # Verify that
    HttpSignature.verify_request(fake_request, keypair["public_key"], skip_date=True)
