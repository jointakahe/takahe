from django.core.files import File
from django.shortcuts import get_object_or_404

from activities.models import PostAttachment, PostAttachmentStates
from api import schemas
from core.files import blurhash_image, resize_image
from hatchway import QueryOrBody, api_view

from ..decorators import identity_required


@identity_required
@api_view.post
def upload_media(
    request,
    file: File,
    description: QueryOrBody[str] = "",
    focus: QueryOrBody[str] = "0,0",
) -> schemas.MediaAttachment:
    main_file = resize_image(
        file,
        size=(2000, 2000),
        cover=False,
    )
    thumbnail_file = resize_image(
        file,
        size=(400, 225),
        cover=True,
    )
    attachment = PostAttachment.objects.create(
        blurhash=blurhash_image(thumbnail_file),
        mimetype="image/webp",
        width=main_file.image.width,
        height=main_file.image.height,
        name=description or None,
        state=PostAttachmentStates.fetched,
    )
    attachment.file.save(
        main_file.name,
        main_file,
    )
    attachment.thumbnail.save(
        thumbnail_file.name,
        thumbnail_file,
    )
    attachment.save()
    return schemas.MediaAttachment.from_post_attachment(attachment)


@identity_required
@api_view.get
def get_media(
    request,
    id: str,
) -> schemas.MediaAttachment:
    attachment = get_object_or_404(PostAttachment, pk=id)
    return schemas.MediaAttachment.from_post_attachment(attachment)


@identity_required
@api_view.put
def update_media(
    request,
    id: str,
    description: QueryOrBody[str] = "",
    focus: QueryOrBody[str] = "0,0",
) -> schemas.MediaAttachment:
    attachment = get_object_or_404(PostAttachment, pk=id)
    attachment.name = description or None
    attachment.save()
    return schemas.MediaAttachment.from_post_attachment(attachment)
