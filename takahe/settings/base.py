import os
import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "core",
    "activities",
    "users",
    "stator",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "core.middleware.ConfigLoadingMiddleware",
    "users.middleware.IdentityMiddleware",
]

ROOT_URLCONF = "takahe.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context.config_context",
            ],
        },
    },
]

WSGI_APPLICATION = "takahe.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", 5432),
        "NAME": os.environ.get("PGDATABASE", "takahe"),
        "USER": os.environ.get("PGUSER", "postgres"),
        "PASSWORD": os.environ.get("PGPASSWORD"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

LOGIN_URL = "/auth/login/"
LOGOUT_URL = "/auth/logout/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

ALLOWED_HOSTS = ["*"]

### User-configurable options, pulled from the environment ###

MAIN_DOMAIN = os.environ["TAKAHE_MAIN_DOMAIN"]
if "/" in MAIN_DOMAIN:
    print("TAKAHE_MAIN_DOMAIN should be just the domain name - no https:// or path")
    sys.exit(1)


if os.environ.get("TAKAHE_EMAIL_CONSOLE_ONLY"):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    EMAIL_FROM = "test@example.com"
else:
    EMAIL_FROM = os.environ["TAKAHE_EMAIL_FROM"]
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

# Set up media storage
MEDIA_BACKEND = os.environ.get("TAKAHE_MEDIA_BACKEND", None)
if MEDIA_BACKEND == "local":
    # Note that this MUST be a fully qualified URL in production
    MEDIA_URL = os.environ.get("TAKAHE_MEDIA_URL", "/media/")
    MEDIA_ROOT = os.environ.get("TAKAHE_MEDIA_ROOT", BASE_DIR / "media")
elif MEDIA_BACKEND == "gcs":
    DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
    GS_BUCKET_NAME = os.environ["TAKAHE_MEDIA_BUCKET"]
elif MEDIA_BACKEND == "s3":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_STORAGE_BUCKET_NAME = os.environ["TAKAHE_MEDIA_BUCKET"]
else:
    print("Unknown TAKAHE_MEDIA_BACKEND value")
    sys.exit(1)
