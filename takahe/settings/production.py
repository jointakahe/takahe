import os
import sys
from typing import Optional

from .base import *  # noqa

# Ensure debug features are off
DEBUG = bool(os.environ.get("TAKAHE__SECURITY_HAZARD__DEBUG", False))

# TODO: Allow better setting of allowed_hosts, if we need to
ALLOWED_HOSTS = ["*"]

### User-configurable options, pulled from the environment ###

# Secret key
try:
    SECRET_KEY = os.environ["TAKAHE_SECRET_KEY"]
except KeyError:
    print("You must specify the TAKAHE_SECRET_KEY environment variable!")
    sys.exit(1)

# SSL proxy header
if "TAKAHE_SECURE_HEADER" in os.environ:
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_" + os.environ["TAKAHE_SECURE_HEADER"].replace("-", "_").upper(),
        "https",
    )

# Fallback domain for links
MAIN_DOMAIN = os.environ["TAKAHE_MAIN_DOMAIN"]
if "/" in MAIN_DOMAIN:
    print("TAKAHE_MAIN_DOMAIN should be just the domain name - no https:// or path")
    sys.exit(1)

# Email config
if os.environ.get("TAKAHE_EMAIL_CONSOLE_ONLY"):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    SERVER_EMAIL = "test@example.com"
else:
    SERVER_EMAIL = os.environ["TAKAHE_EMAIL_FROM"]
    if "TAKAHE_EMAIL_SENDGRID_KEY" in os.environ:
        EMAIL_HOST = "smtp.sendgrid.net"
        EMAIL_PORT = 587
        EMAIL_HOST_USER: Optional[str] = "apikey"
        EMAIL_HOST_PASSWORD: Optional[str] = os.environ["TAKAHE_EMAIL_SENDGRID_KEY"]
        EMAIL_USE_TLS = True
    else:
        EMAIL_HOST = os.environ["TAKAHE_EMAIL_HOST"]
        EMAIL_PORT = int(os.environ["TAKAHE_EMAIL_PORT"])
        EMAIL_HOST_USER = os.environ.get("TAKAHE_EMAIL_USER")
        EMAIL_HOST_PASSWORD = os.environ.get("TAKAHE_EMAIL_PASSWORD")
        EMAIL_USE_SSL = EMAIL_PORT == 465
        EMAIL_USE_TLS = EMAIL_PORT == 587

AUTO_ADMIN_EMAIL = os.environ.get("TAKAHE_AUTO_ADMIN_EMAIL")

# Media storage
MEDIA_BACKEND = os.environ.get("TAKAHE_MEDIA_BACKEND", None)
if MEDIA_BACKEND == "local":
    # Note that this MUST be a fully qualified URL in production
    MEDIA_URL = os.environ.get("TAKAHE_MEDIA_URL", "/media/")
    MEDIA_ROOT = os.environ.get("TAKAHE_MEDIA_ROOT", BASE_DIR / "media")
elif MEDIA_BACKEND == "gcs":
    DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
    GS_BUCKET_NAME = os.environ["TAKAHE_MEDIA_BUCKET"]
    GS_QUERYSTRING_AUTH = False
elif MEDIA_BACKEND == "s3":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_STORAGE_BUCKET_NAME = os.environ["TAKAHE_MEDIA_BUCKET"]
else:
    print("Unknown TAKAHE_MEDIA_BACKEND value")
    sys.exit(1)

# Stator secret token
STATOR_TOKEN = os.environ.get("TAKAHE_STATOR_TOKEN")

# Error email recipients
if "TAKAHE_ERROR_EMAILS" in os.environ:
    ADMINS = [("Admin", e) for e in os.environ["TAKAHE_ERROR_EMAILS"].split(",")]

# Sentry integration
if "SENTRY_DSN" in os.environ:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[
            DjangoIntegration(),
        ],
        traces_sample_rate=1.0,
        send_default_pii=True,
    )
    SENTRY_ENABLED = True
