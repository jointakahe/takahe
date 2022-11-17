import base64
import json
from typing import Dict, List, Literal, TypedDict
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes
from django.http import HttpRequest
from django.utils import timezone
from django.utils.http import http_date, parse_http_date
from OpenSSL import crypto
from pyld import jsonld

from core.ld import format_ld_date


class VerificationError(BaseException):
    """
    There was an error with verifying the signature
    """

    pass


class VerificationFormatError(VerificationError):
    """
    There was an error with the format of the signature (not if it is valid)
    """

    pass


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
                value = request.META["HTTP_%s" % header_name.upper().replace("-", "_")]
            headers[header_name] = value
        return "\n".join(f"{name.lower()}: {value}" for name, value in headers.items())

    @classmethod
    def parse_signature(cls, signature: str) -> "HttpSignatureDetails":
        bits = {}
        for item in signature.split(","):
            name, value = item.split("=", 1)
            value = value.strip('"')
            bits[name.lower()] = value
        signature_details: HttpSignatureDetails = {
            "headers": bits["headers"].split(),
            "signature": base64.b64decode(bits["signature"]),
            "algorithm": bits["algorithm"],
            "keyid": bits["keyid"],
        }
        return signature_details

    @classmethod
    def compile_signature(cls, details: "HttpSignatureDetails") -> str:
        value = f'keyId="{details["keyid"]}",headers="'
        value += " ".join(h.lower() for h in details["headers"])
        value += '",signature="'
        value += base64.b64encode(details["signature"]).decode("ascii")
        value += f'",algorithm="{details["algorithm"]}"'
        return value

    @classmethod
    def verify_signature(
        cls,
        signature: bytes,
        cleartext: str,
        public_key: str,
    ):
        x509 = crypto.X509()
        x509.set_pubkey(
            crypto.load_publickey(
                crypto.FILETYPE_PEM,
                public_key.encode("ascii"),
            )
        )
        try:
            crypto.verify(x509, signature, cleartext.encode("ascii"), "sha256")
        except crypto.Error:
            raise VerificationError("Signature mismatch")

    @classmethod
    def verify_request(cls, request, public_key, skip_date=False):
        """
        Verifies that the request has a valid signature for its body
        """
        # Verify body digest
        if "HTTP_DIGEST" in request.META:
            expected_digest = HttpSignature.calculate_digest(request.body)
            if request.META["HTTP_DIGEST"] != expected_digest:
                raise VerificationFormatError("Digest is incorrect")
        # Verify date header
        if "HTTP_DATE" in request.META and not skip_date:
            header_date = parse_http_date(request.META["HTTP_DATE"])
            if abs(timezone.now().timestamp() - header_date) > 60:
                raise VerificationFormatError("Date is too far away")
        # Get the signature details
        if "HTTP_SIGNATURE" not in request.META:
            raise VerificationFormatError("No signature header present")
        signature_details = cls.parse_signature(request.META["HTTP_SIGNATURE"])
        # Reject unknown algorithms
        if signature_details["algorithm"] != "rsa-sha256":
            raise VerificationFormatError("Unknown signature algorithm")
        # Create the signature payload
        headers_string = cls.headers_from_request(request, signature_details["headers"])
        cls.verify_signature(
            signature_details["signature"],
            headers_string,
            public_key,
        )

    @classmethod
    async def signed_request(
        self,
        uri: str,
        body: Dict,
        private_key: str,
        key_id: str,
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
        pkey = crypto.load_privatekey(
            crypto.FILETYPE_PEM,
            private_key.encode("ascii"),
        )
        signature = crypto.sign(
            pkey,
            signed_string.encode("ascii"),
            "sha256",
        )
        headers["Signature"] = self.compile_signature(
            {
                "keyid": key_id,
                "headers": list(headers.keys()),
                "signature": signature,
                "algorithm": "rsa-sha256",
            }
        )
        del headers["(request-target)"]
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                uri,
                headers=headers,
                content=body_bytes,
            )
            if response.status_code >= 400:
                raise ValueError(
                    f"Request error: {response.status_code} {response.content}"
                )
            return response


class HttpSignatureDetails(TypedDict):
    algorithm: str
    headers: List[str]
    signature: bytes
    keyid: str


class LDSignature:
    """
    Creates and verifies signatures of JSON-LD documents
    """

    @classmethod
    def verify_signature(cls, document: Dict, public_key: str) -> None:
        """
        Verifies a document
        """
        try:
            # Strip out the signature from the incoming document
            signature = document.pop("signature")
            # Create the options document
            options = {
                "@context": "https://w3id.org/identity/v1",
                "creator": signature["creator"],
                "created": signature["created"],
            }
        except KeyError:
            raise VerificationFormatError("Invalid signature section")
        if signature["type"].lower() != "rsasignature2017":
            raise VerificationFormatError("Unknown signature type")
        # Get the normalised hash of each document
        final_hash = cls.normalized_hash(options) + cls.normalized_hash(document)
        # Verify the signature
        x509 = crypto.X509()
        x509.set_pubkey(
            crypto.load_publickey(
                crypto.FILETYPE_PEM,
                public_key.encode("ascii"),
            )
        )
        try:
            crypto.verify(
                x509,
                base64.b64decode(signature["signatureValue"]),
                final_hash,
                "sha256",
            )
        except crypto.Error:
            raise VerificationError("Signature mismatch")

    @classmethod
    def create_signature(
        cls, document: Dict, private_key: str, key_id: str
    ) -> Dict[str, str]:
        """
        Creates the signature for a document
        """
        # Create the options document
        options: Dict[str, str] = {
            "@context": "https://w3id.org/identity/v1",
            "creator": key_id,
            "created": format_ld_date(timezone.now()),
        }
        # Get the normalised hash of each document
        final_hash = cls.normalized_hash(options) + cls.normalized_hash(document)
        # Create the signature
        pkey = crypto.load_privatekey(
            crypto.FILETYPE_PEM,
            private_key.encode("ascii"),
        )
        signature = base64.b64encode(crypto.sign(pkey, final_hash, "sha256"))
        # Add it to the options document along with other bits
        options["signatureValue"] = signature.decode("ascii")
        options["type"] = "RsaSignature2017"
        return options

    @classmethod
    def normalized_hash(cls, document) -> bytes:
        """
        Takes a JSON-LD document and create a hash of its URDNA2015 form,
        in the same way that Mastodon does internally.

        Reference: https://socialhub.activitypub.rocks/t/making-sense-of-rsasignature2017/347
        """
        norm_form = jsonld.normalize(
            document,
            {"algorithm": "URDNA2015", "format": "application/n-quads"},
        )
        digest = hashes.Hash(hashes.SHA256())
        digest.update(norm_form.encode("utf8"))
        return digest.finalize().hex().encode("ascii")
