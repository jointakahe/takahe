import os

from .base import *  # noqa

# Load secret key from environment with a fallback
SECRET_KEY = os.environ.get("TAKAHE_SECRET_KEY", "insecure_secret")

# Disable the CRSF origin protection
MIDDLEWARE.insert(0, "core.middleware.AlwaysSecureMiddleware")

# Ensure debug features are on
DEBUG = True
CRISPY_FAIL_SILENTLY = False
