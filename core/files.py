import io

import blurhash
import httpx
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from PIL import Image, ImageOps


class ImageFile(File):
    image: Image


def resize_image(
    image: File,
    *,
    size: tuple[int, int],
    cover=True,
    keep_format=False,
) -> ImageFile:
    """
    Resizes an image to fit insize the given size (cropping one dimension
    to fit if needed)
    """
    with Image.open(image) as img:
        if cover:
            resized_image = ImageOps.fit(img, size, method=Image.Resampling.BILINEAR)
        else:
            resized_image = img.copy()
            resized_image.thumbnail(size, resample=Image.Resampling.BILINEAR)
        new_image_bytes = io.BytesIO()
        if keep_format:
            resized_image.save(new_image_bytes, format=img.format)
            file = ImageFile(new_image_bytes)
        else:
            resized_image.save(new_image_bytes, format="webp")
            file = ImageFile(new_image_bytes, name="image.webp")
        file.image = resized_image
        return file


def blurhash_image(file) -> str:
    """
    Returns the blurhash for an image
    """
    return blurhash.encode(file, 4, 4)


async def get_remote_file(
    url: str,
    *,
    timeout: float = settings.SETUP.REMOTE_TIMEOUT,
    max_size: int | None = None,
) -> tuple[File | None, str | None]:
    """
    Download a URL and return the File and content-type.
    """
    headers = {
        "User-Agent": settings.TAKAHE_USER_AGENT,
    }

    async with httpx.AsyncClient(headers=headers) as client:
        async with client.stream("GET", url, timeout=timeout) as stream:
            allow_download = max_size is None
            if max_size:
                try:
                    content_length = int(stream.headers["content-length"])
                    allow_download = content_length <= max_size
                except (KeyError, TypeError):
                    pass
            if allow_download:
                file = ContentFile(await stream.aread(), name=url)
                return file, stream.headers.get(
                    "content-type", "application/octet-stream"
                )

    return None, None
