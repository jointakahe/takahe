import pytest
from asgiref.sync import async_to_sync
from django.test.client import RequestFactory
from pytest_httpx import HTTPXMock

from core.signatures import HttpSignature, LDSignature, VerificationError

# Our testing-only keypair
private_key = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCzNJa9JIxQpOtQ
z8UQKXDPREF9DyBliGu3uPWo6DMnkOm7hoh2+nOryrWDqWOFaVK//n7kltHXUEbm
U3exh0/0iWfzx2AbNrI04csAvW/hRvHbHBnVTotSxzqTd3ESkpcSW4xVuz9aCcFR
kW3unSCO3fF0Lh8Jsy9N/CT6oTnwG+ZpeGvHVbh9xfR5Ww6zA7z8A6B17hbzdMd/
3qUPijyIb5se4cWVtGg/ZJ0X1syn9u9kpwUjhHlyWH/esMRHxPuW49BPZPhhKs1+
t//4xgZcRX515qFqPS2EtYgZAfh7M3TRv8uCSzL4TT+8ka9IUwKdV6TFaqH27bAG
KyJQfGaTAgMBAAECggEALZY5qFjlRtiFMfQApdlc5KTw4d7Yt2tqN3zaJUMYTD7d
boJNMbMJfNCetyT+d6Aw2D1ly0GglNzLhGkEQElzKfpQUt/Lj3CtCa3Mpd4K2Wxi
NwJhgfUulPqwaHYQchCPVLCsNNziw0VLA7Rymionb6B+/TaEV8PYy0ZSo90ir3UD
CL5t+IWgIPiy6pk1wGOmeB+tU4+V7/hFel+vPFNahafqVhLE311dfx2aOfweAEfN
e4JoPeJP1/fB+BVZMyVSAraKz6wheymBBNKKn/vpFsdd6it2AP4UZeFp6ma9wT9t
nk65IpHg1MBxazQd7621GrPH+ZnhMg62H/FEj6rIDQKBgQC1w1fEbk+zjI54DXU8
FAe5cJbZS89fMP5CtzlWKzTzfdaavT+5cUYp3XAv37tSGsqYAXxY+4bHGa+qdCQO
I41cmylWGNX2e29/p2BspDPM6YQ0Z21MxFRBTWvHFrhd0bF1cXKBKPttdkKvzOEP
6uNy+/QtRNn9xF/ZjaMHcyPPTQKBgQD8ZdOmZ3TMsYJchAjjseN8S+Objw2oZzmK
6I1ULJBz3DWiyCUfir+pMjSH4fsAf9zrHkiM7xUgMByTukVRt16BrT7TlEBanAxc
/AKdNB3f0pza829LCz1lMAUn+ngZLTmRR+1rQFXqTjhB+0peJzKiMli+9BBhL9Ry
jMeTuLHdXwKBgGiz9kL5KIBNX2RYnEfXYfu4l6zktrgnCNB1q1mv2fjJbG4GxkaU
sc47+Pwa7VUGid22PWMkwSa/7SlLbdmXMT8/QjiOZfJueHQYfrsWe6B2g+mMCrJG
BiL37jXpKJsiyA7XIxaz/OG5VgDfDGaW8B60dJv/JXPBQ1WW+Wq5MM+hAoGAAUdS
xykHAnJzwpw4n06rZFnOEV+sJgo/1GBRNvfy02NuMiDpbzt4tRa4BWgzqVD8gYRp
wa0EYmFcA7OR3lQbenSyOMgre0oHFgGA0eMNs7CRctqA2dR4vyZ7IDS4nwgHnqDK
pxxwUvuKdWsceVWhgAjZQj5iRtvDK8Fi0XDCFekCgYALTU1v5iMIpaRAe+eyA2B1
42qm4B/uhXznvOu2YXU6iJFmMgHGYgpa+Dq8uUjKtpn/LIFeX1KN0hH8z/0LW3gB
e7tN7taW0oLK3RQcEMfkZ7diE9x3LGqo/xMxsZMtxAr88p5eMEU/nxxznOqq+W9b
qxRbXYzEtHz+cW9+FZkyVw==
-----END PRIVATE KEY-----"""

public_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAszSWvSSMUKTrUM/FEClw
z0RBfQ8gZYhrt7j1qOgzJ5Dpu4aIdvpzq8q1g6ljhWlSv/5+5JbR11BG5lN3sYdP
9Iln88dgGzayNOHLAL1v4Ubx2xwZ1U6LUsc6k3dxEpKXEluMVbs/WgnBUZFt7p0g
jt3xdC4fCbMvTfwk+qE58BvmaXhrx1W4fcX0eVsOswO8/AOgde4W83THf96lD4o8
iG+bHuHFlbRoP2SdF9bMp/bvZKcFI4R5clh/3rDER8T7luPQT2T4YSrNfrf/+MYG
XEV+deahaj0thLWIGQH4ezN00b/Lgksy+E0/vJGvSFMCnVekxWqh9u2wBisiUHxm
kwIDAQAB
-----END PUBLIC KEY-----"""

public_key_id = "https://example.com/test-actor#test-key"


def test_sign_ld():
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
        private_key,
        public_key_id,
    )
    # Check it and assign it to the document
    assert "signatureValue" in signature_section
    assert signature_section["type"] == "RsaSignature2017"
    document["signature"] = signature_section
    # Now verify it ourselves
    LDSignature.verify_signature(document, public_key)


def test_verifying_ld():
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
    LDSignature.verify_signature(document, public_key)
    # Mutate it slightly and ensure it does not verify
    with pytest.raises(VerificationError):
        document["actor"] = "https://example.com/evil-actor"
        LDSignature.verify_signature(document, public_key)


def test_sign_http(httpx_mock: HTTPXMock):
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
    async_to_sync(HttpSignature.signed_request)(
        uri="https://example.com/test-actor",
        body=document,
        private_key=private_key,
        key_id=public_key_id,
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
    HttpSignature.verify_request(fake_request, public_key)


def test_verify_http():
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
    HttpSignature.verify_request(fake_request, public_key, skip_date=True)
