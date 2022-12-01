import base64
import os

from django.utils import timezone


def upload_namer(prefix, instance, filename):
    """
    Names uploaded images, obscuring their original name with a random UUID.
    """
    now = timezone.now()
    _, old_extension = os.path.splitext(filename)
    new_filename = base64.b32encode(os.urandom(15)).decode("ascii").lower()
    return f"{prefix}/{now.year}/{now.month}/{now.day}/{new_filename}{old_extension}"
