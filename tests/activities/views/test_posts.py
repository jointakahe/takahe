import re

import mock
import pytest

from activities.views.posts import Compose


@pytest.mark.django_db
def test_content_warning_text(identity, user, rf, config_system):
    request = rf.get("/compose/")
    request.user = user
    request.identity = identity

    config_system.content_warning_text = "Content Summary"
    with mock.patch("core.models.Config.load_system", return_value=config_system):
        view = Compose.as_view()
        resp = view(request)
        assert resp.status_code == 200
        content = str(resp.rendered_content)
        assert 'placeholder="Content Summary"' in content
        assert re.search(
            r"<label.*>\s*Content Summary\s*</label>", content, flags=re.MULTILINE
        )
