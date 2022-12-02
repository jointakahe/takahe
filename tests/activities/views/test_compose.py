import re

import mock
import pytest
from django.core.exceptions import PermissionDenied

from activities.models import Post
from activities.views.compose import Compose


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


@pytest.mark.django_db
def test_post_edit_security(identity, user, rf, other_identity):
    # Create post
    other_post = Post.objects.create(
        content="<p>OTHER POST!</p>",
        author=other_identity,
        local=True,
        visibility=Post.Visibilities.public,
    )

    request = rf.get(other_post.get_absolute_url() + "edit/")
    request.user = user
    request.identity = identity

    view = Compose.as_view()
    with pytest.raises(PermissionDenied) as ex:
        view(request, handle=other_identity.handle.lstrip("@"), post_id=other_post.id)
    assert str(ex.value) == "Post author is not requestor"
