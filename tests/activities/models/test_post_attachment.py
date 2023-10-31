import pytest
from django.core.files.base import ContentFile

from activities.models import Post, PostAttachment, PostAttachmentStates
from core.files import resize_image


@pytest.mark.django_db
def test_remote_attachment(remote_identity, config_system):
    """
    Tests that remote post attachments and their metadata work
    """

    post = Post.by_ap(
        data={
            "id": "https://remote.test/posts/1",
            "type": "Note",
            "content": "Hi World",
            "attributedTo": remote_identity.actor_uri,
            "published": "2022-12-23T10:50:54Z",
            "attachment": {
                "type": "Image",
                "url": "https://remote.test/posts/1/attachment/1",
                "focalPoint": [-0.5, 0.25],
                "mediaType": "image/png",
                "name": "Test attachment",
                "width": 100,
                "height": 100,
            },
        },
        create=True,
    )
    attachment = post.attachments.first()
    assert attachment.remote_url == "https://remote.test/posts/1/attachment/1"
    assert attachment.name == "Test attachment"
    assert attachment.focal_x == -0.5
    assert attachment.focal_y == 0.25

    mastodon = post.to_mastodon_json()

    assert mastodon["media_attachments"][0]["description"] == "Test attachment"
    assert mastodon["media_attachments"][0]["meta"]["focus"]["x"] == -0.5
    assert mastodon["media_attachments"][0]["meta"]["focus"]["y"] == 0.25


@pytest.mark.django_db
def test_local_attachment(identity, config_system):
    """
    Tests that local post attachments and their metadata work
    """
    attachments = []
    attachment = PostAttachment.objects.create(
        mimetype="image/png",
        name="Test attachment",
        author=identity,
        width=100,
        height=100,
        focal_x=-0.5,
        focal_y=0.25,
        state=PostAttachmentStates.fetched,
    )
    # 1x1 PNG
    file = resize_image(
        # 1x1 PNG
        ContentFile(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x01\x03\x00\x00\x00%\xdbV\xca\x00\x00\x00\x03PLTE\x00\x00\x00\xa7z=\xda\x00\x00\x00\x01tRNS\x00@\xe6\xd8f\x00\x00\x00\nIDAT\x08\xd7c`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        ),
        size=(100, 100),
        cover=False,
    )
    attachment.file.save(file.name, file)
    attachments.append(attachment)
    # another copy of the attachment without a focal point
    attachment2 = PostAttachment.objects.create(
        mimetype="image/png",
        name="Test attachment 2",
        author=identity,
        width=100,
        height=100,
        state=PostAttachmentStates.fetched,
    )
    attachment2.file.save(file.name, file)
    attachments.append(attachment2)
    # Create the post
    post = Post.create_local(
        author=identity,
        content="Hi World",
        attachments=attachments,
    )

    attachments = post.attachments.all()
    # first attachment has a focal point
    assert attachments[0].name == "Test attachment"
    assert attachments[0].focal_x == -0.5
    assert attachments[0].focal_y == 0.25
    # second attachment doesn't have a focal point
    assert attachments[1].name == "Test attachment 2"
    assert attachments[1].focal_x is None
    assert attachments[1].focal_y is None

    # same in the AP JSON
    ap = post.to_ap()

    # first attachment has a focal point
    assert ap["attachment"][0]["name"] == "Test attachment"
    assert ap["attachment"][0]["focalPoint"][0] == -0.5
    assert ap["attachment"][0]["focalPoint"][1] == 0.25

    # second attachment doesn't have a focal point
    assert ap["attachment"][1]["name"] == "Test attachment 2"
    assert "focalPoint" not in ap["attachment"][1]
