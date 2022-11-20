import mock
import pytest

from activities.views.timelines import Home


@pytest.mark.django_db
def test_content_warning_text(identity, user, rf, config_system):
    request = rf.get("/")
    request.user = user
    request.identity = identity

    config_system.content_warning_text = "Content Summary"
    with mock.patch("core.models.Config.load_system", return_value=config_system):
        view = Home.as_view()
        resp = view(request)
        assert resp.status_code == 200
        assert 'placeholder="Content Summary"' in str(resp.rendered_content)
