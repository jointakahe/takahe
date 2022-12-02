import pytest
from django.core.exceptions import PermissionDenied

from activities.models import Post
from activities.views.posts import Delete


@pytest.mark.django_db
def test_post_delete_security(identity, user, rf, other_identity):
    # Create post
    other_post = Post.objects.create(
        content="<p>OTHER POST!</p>",
        author=other_identity,
        local=True,
        visibility=Post.Visibilities.public,
    )

    request = rf.post(other_post.get_absolute_url() + "delete/")
    request.user = user
    request.identity = identity

    view = Delete.as_view()
    with pytest.raises(PermissionDenied) as ex:
        view(request, handle=other_identity.handle.lstrip("@"), post_id=other_post.id)
    assert str(ex.value) == "Post author is not requestor"
