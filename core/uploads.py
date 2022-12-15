import os
import secrets

from django.utils import timezone
from storages.backends.gcloud import GoogleCloudStorage
from storages.backends.s3boto3 import S3Boto3Storage


def upload_namer(prefix, instance, filename):
    """
    Names uploaded images, obscuring their original name with a random UUID.
    """
    now = timezone.now()
    _, old_extension = os.path.splitext(filename)
    new_filename = secrets.token_urlsafe(20)
    return f"{prefix}/{now.year}/{now.month}/{now.day}/{new_filename}{old_extension}"


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
