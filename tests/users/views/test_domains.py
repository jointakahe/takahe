import pytest
from django.core.exceptions import ValidationError

from users.views.admin.domains import DomainValidator

VALID_DOMAINS = [
    "takahe.social",
    "subdomain.takahe.social",
    "another.subdomain.takahe.social",
    "jointakahe.org",
    "xn--c6h.com",
    "takahe.xn--social",
    "example.com",
    "www.example.com",
    "example.co.uk",
]

INVALID_DOMAINS = [
    "example.c",
    "example,com",
    "example,com.com",
    "example",
    ".com",
    "example.com/example",
    "-example.com",
    "example-.com",
    "example.com-",
    "https://example.com",
]


@pytest.mark.parametrize("domain", VALID_DOMAINS)
def test_domain_validation_accepts_valid_domains(domain):
    """
    Tests that the domain validator works in positive cases
    """
    DomainValidator()(domain)


@pytest.mark.parametrize("domain", INVALID_DOMAINS)
def test_domain_validation_raises_exception_for_invalid_domains(domain):
    """
    Tests that the domain validator works in negative cases
    """
    with pytest.raises(ValidationError):
        DomainValidator()(domain)
