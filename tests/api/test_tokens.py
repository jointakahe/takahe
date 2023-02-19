import pytest


@pytest.mark.django_db
def test_has_scope(api_token):
    """
    Tests has_scope on the Token model
    """
    assert api_token.has_scope("read")
    assert api_token.has_scope("read:statuses")
    assert not api_token.has_scope("destroyearth")
