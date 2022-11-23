import os
import sys

from .base import *  # noqa

# Load secret key from environment with a fallback
SECRET_KEY = os.environ.get("TAKAHE_SECRET_KEY", "insecure_secret")

# Ensure debug features are on
DEBUG = True

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "https://127.0.0.1:8000",
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SERVER_EMAIL = "test@example.com"

MAIN_DOMAIN = os.environ.get("TAKAHE_MAIN_DOMAIN", "example.com")
if "/" in MAIN_DOMAIN:
    print("TAKAHE_MAIN_DOMAIN should be just the domain name - no https:// or path")
    sys.exit(1)

MEDIA_URL = os.environ.get("TAKAHE_MEDIA_URL", "/media/")
MEDIA_ROOT = os.environ.get("TAKAHE_MEDIA_ROOT", BASE_DIR / "media")
