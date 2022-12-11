import io

import blurhash
from django.core.files import File
from PIL import Image, ImageOps


def resize_image(
    image: File,
    *,
    size: tuple[int, int],
    cover=True,
    keep_format=False,
) -> File:
    """
    Resizes an image to fit insize the given size (cropping one dimension
    to fit if needed)
    """
    with Image.open(image) as img:
        if cover:
            resized_image = ImageOps.fit(img, size)
        else:
            resized_image = ImageOps.contain(img, size)
        new_image_bytes = io.BytesIO()
        if keep_format:
            resized_image.save(new_image_bytes, format=image.format)
            file = File(new_image_bytes)
        else:
            resized_image.save(new_image_bytes, format="webp")
            file = File(new_image_bytes, name="image.webp")
        file.image = resized_image
        return file


def blurhash_image(file) -> str:
    """
    Returns the blurhash for an image
    """
    return blurhash.encode(file, 4, 4)
