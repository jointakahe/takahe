import os

from .base import *  # noqa

# Load secret key from environment with a fallback
SECRET_KEY = os.environ.get("TAKAHE_SECRET_KEY", "insecure_secret")

# Disable the CRSF origin protection
MIDDLEWARE.insert(0, "core.middleware.AlwaysSecureMiddleware")

# Ensure debug features are on
DEBUG = True

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "https://127.0.0.1:8000",
]
