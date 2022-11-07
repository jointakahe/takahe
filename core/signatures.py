import base64
import json
from typing import Dict, List, Literal, TypedDict
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes
from django.http import HttpRequest
from django.utils.http import http_date

from users.models import Identity


class HttpSignature:
    """
    Allows for calculation and verification of HTTP signatures
    """

    @classmethod
    def calculate_digest(cls, data, algorithm="sha-256") -> str:
        """
        Calculates the digest header value for a given HTTP body
        """
        if algorithm == "sha-256":
            digest = hashes.Hash(hashes.SHA256())
            digest.update(data)
            return "SHA-256=" + base64.b64encode(digest.finalize()).decode("ascii")
        else:
            raise ValueError(f"Unknown digest algorithm {algorithm}")

    @classmethod
    def headers_from_request(cls, request: HttpRequest, header_names: List[str]) -> str:
        """
        Creates the to-be-signed header payload from a Django request
        """
        headers = {}
        for header_name in header_names:
            if header_name == "(request-target)":
                value = f"post {request.path}"
            elif header_name == "content-type":
                value = request.META["CONTENT_TYPE"]
            else:
                value = request.META[f"HTTP_{header_name.upper()}"]
            headers[header_name] = value
        return "\n".join(f"{name.lower()}: {value}" for name, value in headers.items())

    @classmethod
    def parse_signature(cls, signature: str) -> "SignatureDetails":
        bits = {}
        for item in signature.split(","):
            name, value = item.split("=", 1)
            value = value.strip('"')
            bits[name.lower()] = value
        signature_details: SignatureDetails = {
            "headers": bits["headers"].split(),
            "signature": base64.b64decode(bits["signature"]),
            "algorithm": bits["algorithm"],
            "keyid": bits["keyid"],
        }
        return signature_details

    @classmethod
    def compile_signature(cls, details: "SignatureDetails") -> str:
        value = f'keyId="{details["keyid"]}",headers="'
        value += " ".join(h.lower() for h in details["headers"])
        value += '",signature="'
        value += base64.b64encode(details["signature"]).decode("ascii")
        value += f'",algorithm="{details["algorithm"]}"'
        return value

    @classmethod
    async def signed_request(
        self,
        uri: str,
        body: Dict,
        identity: Identity,
        content_type: str = "application/json",
        method: Literal["post"] = "post",
    ):
        """
        Performs an async request to the given path, with a document, signed
        as an identity.
        """
        uri_parts = urlparse(uri)
        date_string = http_date()
        body_bytes = json.dumps(body).encode("utf8")
        headers = {
            "(request-target)": f"{method} {uri_parts.path}",
            "Host": uri_parts.hostname,
            "Date": date_string,
            "Digest": self.calculate_digest(body_bytes),
            "Content-Type": content_type,
        }
        signed_string = "\n".join(
            f"{name.lower()}: {value}" for name, value in headers.items()
        )
        headers["Signature"] = self.compile_signature(
            {
                "keyid": identity.urls.key.full(),  # type:ignore
                "headers": list(headers.keys()),
                "signature": identity.sign(signed_string),
                "algorithm": "rsa-sha256",
            }
        )
        del headers["(request-target)"]
        async with httpx.AsyncClient() as client:
            print(f"Calling {method} {uri}")
            print(body)
            return await client.request(
                method,
                uri,
                headers=headers,
                content=body_bytes,
            )


class SignatureDetails(TypedDict):
    algorithm: str
    headers: List[str]
    signature: bytes
    keyid: str
