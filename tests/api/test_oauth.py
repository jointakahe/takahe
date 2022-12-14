from api.models import Application


def test_scope_subset():
    app = Application(scopes="read")
    assert app.is_scope_subset("read")
    assert app.is_scope_subset("")

    app.scopes = "read write follow push"
    app.is_scope_subset("read write")
    app.is_scope_subset("read push")
