import pytest

from users.models import Domain
from users.services import DomainService


@pytest.mark.django_db
def test_block():
    DomainService.block(["block1.example.com", "block2.example.com"])

    assert Domain.objects.filter(blocked=True).count() == 2
