import pytest

from users.models import Domain


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
