import base64
import json
from ssl import SSLCertVerificationError, SSLError
from typing import Literal, TypedDict, cast
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from django.utils.http import http_date, parse_http_date
from httpx._types import TimeoutTypes
from idna.core import InvalidCodepoint
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


class RsaKeys:
    @classmethod
    def generate_keypair(cls) -> tuple[str, str]:
        """
        Generates a new RSA keypair
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        private_key_serialized = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        public_key_serialized = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )
        return private_key_serialized, public_key_serialized


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
    def headers_from_request(cls, request: HttpRequest, header_names: list[str]) -> str:
        """
        Creates the to-be-signed header payload from a Django request
        """
        headers = {}
        for header_name in header_names:
            if header_name == "(request-target)":
                value = f"{request.method.lower()} {request.path}"
            elif header_name == "content-type":
                value = request.headers["content-type"]
            elif header_name == "content-length":
                value = request.headers["content-length"]
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
        try:
            signature_details: HttpSignatureDetails = {
                "headers": bits["headers"].split(),
                "signature": base64.b64decode(bits["signature"]),
                "algorithm": bits["algorithm"],
                "keyid": bits["keyid"],
            }
        except KeyError as e:
            key_names = " ".join(bits.keys())
            raise VerificationError(
                f"Missing item from details (have: {key_names}, error: {e})"
            )
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
        public_key_instance: rsa.RSAPublicKey = cast(
            rsa.RSAPublicKey,
            serialization.load_pem_public_key(public_key.encode("ascii")),
        )
        try:
            public_key_instance.verify(
                signature,
                cleartext.encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise VerificationError("Signature mismatch")

    @classmethod
    def verify_request(cls, request, public_key, skip_date=False):
        """
        Verifies that the request has a valid signature for its body
        """
        # Verify body digest
        if "digest" in request.headers:
            expected_digest = HttpSignature.calculate_digest(request.body)
            if request.headers["digest"] != expected_digest:
                raise VerificationFormatError("Digest is incorrect")
        # Verify date header
        if "date" in request.headers and not skip_date:
            header_date = parse_http_date(request.headers["date"])
            if abs(timezone.now().timestamp() - header_date) > 60:
                raise VerificationFormatError("Date is too far away")
        # Get the signature details
        if "signature" not in request.headers:
            raise VerificationFormatError("No signature header present")
        signature_details = cls.parse_signature(request.headers["signature"])
        # Reject unknown algorithms
        # hs2019 is used by some libraries to obfuscate the real algorithm per the spec
        # https://datatracker.ietf.org/doc/html/draft-cavage-http-signatures-12
        if (
            signature_details["algorithm"] != "rsa-sha256"
            and signature_details["algorithm"] != "hs2019"
        ):
            raise VerificationFormatError("Unknown signature algorithm")
        # Create the signature payload
        headers_string = cls.headers_from_request(request, signature_details["headers"])
        cls.verify_signature(
            signature_details["signature"],
            headers_string,
            public_key,
        )

    @classmethod
    def signed_request(
        cls,
        uri: str,
        body: dict | None,
        private_key: str,
        key_id: str,
        content_type: str = "application/json",
        method: Literal["get", "post"] = "post",
        timeout: TimeoutTypes = settings.SETUP.REMOTE_TIMEOUT,
    ):
        """
        Performs an async request to the given path, with a document, signed
        as an identity.
        """
        if "://" not in uri:
            raise ValueError("URI does not contain a scheme")
        # Create the core header field set
        uri_parts = urlparse(uri)
        date_string = http_date()
        headers = {
            "(request-target)": f"{method} {uri_parts.path}",
            "Host": uri_parts.hostname,
            "Date": date_string,
        }
        # If we have a body, add a digest and content type
        if body is not None:
            body_bytes = json.dumps(body).encode("utf8")
            headers["Digest"] = cls.calculate_digest(body_bytes)
            headers["Content-Type"] = content_type
        else:
            body_bytes = b""
        # GET requests get implicit accept headers added
        if method == "get":
            headers["Accept"] = "application/ld+json"
        # Sign the headers
        signed_string = "\n".join(
            f"{name.lower()}: {value}" for name, value in headers.items()
        )
        private_key_instance: rsa.RSAPrivateKey = cast(
            rsa.RSAPrivateKey,
            serialization.load_pem_private_key(
                private_key.encode("ascii"),
                password=None,
            ),
        )
        signature = private_key_instance.sign(
            signed_string.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        headers["Signature"] = cls.compile_signature(
            {
                "keyid": key_id,
                "headers": list(headers.keys()),
                "signature": signature,
                "algorithm": "rsa-sha256",
            }
        )

        # Announce ourselves with an agent similar to Mastodon
        headers["User-Agent"] = settings.TAKAHE_USER_AGENT

        # Send the request with all those headers except the pseudo one
        del headers["(request-target)"]
        with httpx.Client(timeout=timeout) as client:
            try:
                response = client.request(
                    method,
                    uri,
                    headers=headers,
                    content=body_bytes,
                    follow_redirects=method == "get",
                )
            except SSLError as invalid_cert:
                # Not our problem if the other end doesn't have proper SSL
                print(f"{uri} {invalid_cert}")
                raise SSLCertVerificationError(invalid_cert) from invalid_cert
            except InvalidCodepoint as ex:
                # Convert to a more generic error we handle
                raise httpx.HTTPError(f"InvalidCodepoint: {str(ex)}") from None

            if (
                method == "post"
                and response.status_code >= 400
                and response.status_code < 500
                and response.status_code != 404
            ):
                raise ValueError(
                    f"POST error to {uri}: {response.status_code} {response.content!r}"
                )
            return response


class HttpSignatureDetails(TypedDict):
    algorithm: str
    headers: list[str]
    signature: bytes
    keyid: str


class LDSignature:
    """
    Creates and verifies signatures of JSON-LD documents
    """

    @classmethod
    def verify_signature(cls, document: dict, public_key: str) -> None:
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
        public_key_instance: rsa.RSAPublicKey = cast(
            rsa.RSAPublicKey,
            serialization.load_pem_public_key(public_key.encode("ascii")),
        )
        try:
            public_key_instance.verify(
                base64.b64decode(signature["signatureValue"]),
                final_hash,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            raise VerificationError("Signature mismatch")

    @classmethod
    def create_signature(
        cls, document: dict, private_key: str, key_id: str
    ) -> dict[str, str]:
        """
        Creates the signature for a document
        """
        # Create the options document
        options: dict[str, str] = {
            "@context": "https://w3id.org/identity/v1",
            "creator": key_id,
            "created": format_ld_date(timezone.now()),
        }
        # Get the normalised hash of each document
        final_hash = cls.normalized_hash(options) + cls.normalized_hash(document)
        # Create the signature
        private_key_instance: rsa.RSAPrivateKey = cast(
            rsa.RSAPrivateKey,
            serialization.load_pem_private_key(
                private_key.encode("ascii"),
                password=None,
            ),
        )
        signature = base64.b64encode(
            private_key_instance.sign(
                final_hash,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        )
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
