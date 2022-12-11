from django.shortcuts import get_object_or_404
from ninja import File, Schema
from ninja.files import UploadedFile

from activities.models import PostAttachment, PostAttachmentStates
from api import schemas
from api.views.base import api_router
from core.files import blurhash_image, resize_image

from ..decorators import identity_required


class UploadMediaSchema(Schema):
    description: str = ""
    focus: str = "0,0"


@api_router.post("/v1/media", response=schemas.MediaAttachment)
@api_router.post("/v2/media", response=schemas.MediaAttachment)
@identity_required
def upload_media(
    request,
    file: UploadedFile = File(...),
    details: UploadMediaSchema | None = None,
):
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
        name=details.description if details else None,
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
    return attachment.to_mastodon_json()


@api_router.get("/v1/media/{id}", response=schemas.MediaAttachment)
@identity_required
def get_media(
    request,
    id: str,
):
    attachment = get_object_or_404(PostAttachment, pk=id)
    return attachment.to_mastodon_json()


@api_router.put("/v1/media/{id}", response=schemas.MediaAttachment)
@identity_required
def update_media(
    request,
    id: str,
    details: UploadMediaSchema | None = None,
):
    attachment = get_object_or_404(PostAttachment, pk=id)
    attachment.name = details.description if details else None
    attachment.save()
    return attachment.to_mastodon_json()
