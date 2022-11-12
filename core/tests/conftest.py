import pytest
from pyld import jsonld

from core.ld import builtin_document_loader


@pytest.fixture(scope="session", autouse=True)
def ldloader():
    jsonld.set_document_loader(builtin_document_loader)
