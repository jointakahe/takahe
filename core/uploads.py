import os
import secrets
from typing import TYPE_CHECKING

from django.utils import timezone
from storages.backends.gcloud import GoogleCloudStorage
from storages.backends.s3boto3 import S3Boto3Storage

if TYPE_CHECKING:
    from activities.models import Emoji


def upload_namer(prefix, instance, filename):
    """
    Names uploaded images.

    By default, obscures the original name with a random UUID.
    """
    _, old_extension = os.path.splitext(filename)
    new_filename = secrets.token_urlsafe(20)
    now = timezone.now()
    return f"{prefix}/{now.year}/{now.month}/{now.day}/{new_filename}{old_extension}"


def upload_emoji_namer(prefix, instance: "Emoji", filename):
    """
    Names uploaded emoji per domain
    """
    _, old_extension = os.path.splitext(filename)
    if instance.domain is None:
        domain = "_default"
    else:
        domain = instance.domain.domain
    return f"{prefix}/{domain}/{instance.shortcode}{old_extension}"


class TakaheS3Storage(S3Boto3Storage):
    """
    Custom override backend that makes webp files store correctly
    """

    def get_object_parameters(self, name: str):
        params = self.object_parameters.copy()
        if name.endswith(".webp"):
            params["ContentDisposition"] = "inline"
            params["ContentType"] = "image/webp"
        return params


class TakaheGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom override backend that makes webp files store correctly
    """

    def get_object_parameters(self, name: str):
        params = self.object_parameters.copy()
        if name.endswith(".webp"):
            params["content_disposition"] = "inline"
            params["content_type"] = "image/webp"
        return params
