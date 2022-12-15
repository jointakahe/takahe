from api.models import has_required_scopes


def test_has_required_scopes():
    assert has_required_scopes("read", required="")
    assert has_required_scopes("read", required=None)
    assert has_required_scopes("read", required="read")
    assert has_required_scopes("read", required={"read"})
    assert has_required_scopes({"read"}, required="read")
    assert has_required_scopes({"read"}, required={"read"})

    assert has_required_scopes("read write follow push", required="read write")
    assert has_required_scopes("read write follow push", required="write push")
