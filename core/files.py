import io

import blurhash
from django.core.files import File
from PIL import Image, ImageOps


def resize_image(image: File, *, size: tuple[int, int]) -> File:
    """
    Resizes an image to fit insize the given size (cropping one dimension
    to fit if needed)
    """
    with Image.open(image) as img:
        resized_image = ImageOps.fit(img, size)
        new_image_bytes = io.BytesIO()
        resized_image.save(new_image_bytes, format=img.format)
        return File(new_image_bytes)


def blurhash_image(image) -> str:
    """
    Returns the blurhash for an image
    """
    return blurhash.encode(image, 4, 4)
