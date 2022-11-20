import mock
import pytest

from core.models import Config
from users.models import User


@pytest.fixture
def config_system():
    # TODO: Good enough for now, but a better Config mocking system is needed
    result = Config.load_system()
    with mock.patch("core.models.Config.load_system", return_value=result):
        yield result


@pytest.mark.django_db
def test_signup_disabled(client, config_system):
    # Signup disabled and no signup text
    config_system.signup_allowed = False
    resp = client.get("/auth/signup/")
    assert resp.status_code == 200
    content = str(resp.content)
    assert "Not accepting new users at this time" in content
    assert "<button>Create</button>" not in content

    # Signup disabled with signup text configured
    config_system.signup_text = "Go away!!!!!!"
    resp = client.get("/auth/signup/")
    assert resp.status_code == 200
    content = str(resp.content)
    assert "Go away!!!!!!" in content

    # Ensure direct POST doesn't side step guard
    resp = client.post(
        "/auth/signup/", data={"email": "test_signup_disabled@example.org"}
    )
    assert resp.status_code == 200
    assert not User.objects.filter(email="test_signup_disabled@example.org").exists()

    # Signup enabled
    config_system.signup_allowed = True
    resp = client.get("/auth/signup/")
    assert resp.status_code == 200
    content = str(resp.content)
    assert "Not accepting new users at this time" not in content
    assert "<button>Create</button>" in content


@pytest.mark.django_db
def test_signup_invite_only(client, config_system):
    config_system.signup_allowed = True
    config_system.signup_invite_only = True

    resp = client.get("/auth/signup/")
    assert resp.status_code == 200
    content = str(resp.content)
    assert 'name="invite_code"' in content

    # TODO: Actually test this
