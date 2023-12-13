import pytest

from users.models import Domain


def test_valid_domain():
    """
    Tests that a valid domain is valid
    """

    assert Domain.is_valid_domain("example.com")
    assert Domain.is_valid_domain("xn----gtbspbbmkef.xn--p1ai")
    assert Domain.is_valid_domain("underscore_subdomain.example.com")
    assert Domain.is_valid_domain("something.versicherung")
    assert Domain.is_valid_domain("11.com")
    assert Domain.is_valid_domain("a.cn")
    assert Domain.is_valid_domain("sub1.sub2.sample.co.uk")
    assert Domain.is_valid_domain("somerandomexample.xn--fiqs8s")
    assert not Domain.is_valid_domain("über.com")
    assert not Domain.is_valid_domain("example.com:4444")
    assert not Domain.is_valid_domain("example.-com")
    assert not Domain.is_valid_domain("foo@bar.com")
    assert not Domain.is_valid_domain("example.")
    assert not Domain.is_valid_domain("example.com.")
    assert not Domain.is_valid_domain("-example.com")
    assert not Domain.is_valid_domain("_example.com")
    assert not Domain.is_valid_domain("_example._com")
    assert not Domain.is_valid_domain("example_.com")
    assert not Domain.is_valid_domain("example")
    assert not Domain.is_valid_domain("a......b.com")
    assert not Domain.is_valid_domain("a.123")
    assert not Domain.is_valid_domain("123.123")
    assert not Domain.is_valid_domain("123.123.123.123")


@pytest.mark.django_db
def test_recursive_block():
    """
    Tests that blocking a domain also blocks its subdomains
    """

    root_domain = Domain.get_remote_domain("evil.com")
    root_domain.blocked = True
    root_domain.save()

    # Re-fetching the root should be blocked
    assert Domain.get_remote_domain("evil.com").recursively_blocked()

    # A sub domain should also be blocked
    assert Domain.get_remote_domain("terfs.evil.com").recursively_blocked()

    # An unrelated domain should not be blocked
    assert not Domain.get_remote_domain("example.com").recursively_blocked()
