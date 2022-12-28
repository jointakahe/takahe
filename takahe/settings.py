import os
import secrets
import sys
import urllib.parse
from pathlib import Path
from typing import Literal

import dj_database_url
import django_cache_url
import httpx
import sentry_sdk
from pydantic import AnyUrl, BaseSettings, EmailStr, Field, validator
from sentry_sdk.integrations.django import DjangoIntegration

from takahe import __version__

BASE_DIR = Path(__file__).resolve().parent.parent


class CacheBackendUrl(AnyUrl):
    host_required = False
    allowed_schemes = django_cache_url.BACKENDS.keys()


class ImplicitHostname(AnyUrl):
    host_required = False


class MediaBackendUrl(AnyUrl):
    host_required = False
    allowed_schemes = {"s3", "gs", "local"}


def as_bool(v: str | list[str] | None):
    if v is None:
        return False

    if isinstance(v, str):
        v = [v]

    return v[0].lower() in ("true", "yes", "t", "1")


Environments = Literal["development", "production", "test"]

TAKAHE_ENV_FILE = os.environ.get(
    "TAKAHE_ENV_FILE", "test.env" if "pytest" in sys.modules else ".env"
)


class Settings(BaseSettings):
    """
    Pydantic-powered settings, to provide consistent error messages, strong
    typing, consistent prefixes, .venv support, etc.
    """

    #: The default database.
    DATABASE_SERVER: ImplicitHostname | None

    #: The currently running environment, used for things such as sentry
    #: error reporting.
    ENVIRONMENT: Environments = "development"

    #: Should django run in debug mode?
    DEBUG: bool = False

    #: Should the debug toolbar be loaded?
    DEBUG_TOOLBAR: bool = False

    #: Should we atttempt to import the 'local_settings.py'
    LOCAL_SETTINGS: bool = False

    #: Set a secret key used for signing values such as sessions. Randomized
    #: by default, so you'll logout everytime the process restarts.
    SECRET_KEY: str = Field(default_factory=lambda: "autokey-" + secrets.token_hex(128))

    #: Set a secret key used to protect the stator. Randomized by default.
    STATOR_TOKEN: str = Field(default_factory=lambda: secrets.token_hex(128))

    #: If set, a list of allowed values for the HOST header. The default value
    #: of '*' means any host will be accepted.
    ALLOWED_HOSTS: list[str] = Field(default_factory=lambda: ["*"])

    #: If set, a list of hosts to accept for CORS.
    CORS_HOSTS: list[str] = Field(default_factory=list)

    #: If set, a list of hosts to accept for CSRF.
    CSRF_HOSTS: list[str] = Field(default_factory=list)

    #: If enabled, trust the HTTP_X_FORWARDED_FOR header.
    USE_PROXY_HEADERS: bool = False

    #: An optional Sentry DSN for error reporting.
    SENTRY_DSN: str | None = None
    SENTRY_SAMPLE_RATE: float = 1.0
    SENTRY_TRACES_SAMPLE_RATE: float = 0.01
    SENTRY_CAPTURE_MESSAGES: bool = False

    #: Fallback domain for links.
    MAIN_DOMAIN: str = "example.com"

    EMAIL_SERVER: AnyUrl = "console://localhost"
    EMAIL_FROM: EmailStr = "test@example.com"
    AUTO_ADMIN_EMAIL: EmailStr | None = None
    ERROR_EMAILS: list[EmailStr] | None = None

    MEDIA_URL: str = "/media/"
    MEDIA_ROOT: str = str(BASE_DIR / "media")
    MEDIA_BACKEND: MediaBackendUrl | None = None

    #: S3 ACL to apply to all media objects when MEDIA_BACKEND is set to S3. If using a CDN
    #: and/or have public access blocked to buckets this will likely need to be 'private'
    MEDIA_BACKEND_S3_ACL: str = "public-read"

    #: Maximum filesize when uploading images. Increasing this may increase memory utilization
    #: because all images with a dimension greater than 2000px are resized to meet that limit, which
    #: is necessary for compatibility with Mastodon’s image proxy.
    MEDIA_MAX_IMAGE_FILESIZE_MB: int = 10

    #: Maximum filesize for Avatars. Remote avatars larger than this size will
    #: not be fetched and served from media, but served through the image proxy.
    AVATAR_MAX_IMAGE_FILESIZE_KB: int = 1000

    #: Maximum filesize for Emoji. Attempting to upload Local Emoji larger than this size will be
    #: blocked. Remote Emoji larger than this size will not be fetched and served from media, but
    #: served through the image proxy.
    EMOJI_MAX_IMAGE_FILESIZE_KB: int = 200

    #: Request timeouts to use when talking to other servers Either
    #: float or tuple of floats for (connect, read, write, pool)
    REMOTE_TIMEOUT: float | tuple[float, float, float, float] = 5.0

    #: If search features like full text search should be enabled.
    #: (placeholder setting, no effect)
    SEARCH: bool = True

    #: Default cache backend
    CACHES_DEFAULT: CacheBackendUrl | None = None

    # Stator tuning
    STATOR_CONCURRENCY: int = 100
    STATOR_CONCURRENCY_PER_MODEL: int = 40

    PGHOST: str | None = None
    PGPORT: int | None = 5432
    PGNAME: str = "takahe"
    PGUSER: str = "postgres"
    PGPASSWORD: str | None = None

    @validator("PGHOST", always=True)
    def validate_db(cls, PGHOST, values):  # noqa
        if not values.get("DATABASE_SERVER") and not PGHOST:
            raise ValueError("Either DATABASE_SERVER or PGHOST are required.")
        return PGHOST

    class Config:
        env_prefix = "TAKAHE_"
        env_file = str(BASE_DIR / TAKAHE_ENV_FILE)
        env_file_encoding = "utf-8"
        # Case sensitivity doesn't work on Windows, so might as well be
        # consistent from the get-go.
        case_sensitive = False

        # Override the env_prefix so these fields load without TAKAHE_
        fields = {
            "PGHOST": {"env": "PGHOST"},
            "PGPORT": {"env": "PGPORT"},
            "PGNAME": {"env": "PGNAME"},
            "PGUSER": {"env": "PGUSER"},
            "PGPASSWORD": {"env": "PGPASSWORD"},
        }


SETUP = Settings()

# Don't allow automatic keys in production
if SETUP.DEBUG and SETUP.SECRET_KEY.startswith("autokey-"):
    print("You must set TAKAHE_SECRET_KEY in production")
    sys.exit(1)
SECRET_KEY = SETUP.SECRET_KEY
DEBUG = SETUP.DEBUG

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_htmx",
    "core",
    "activities",
    "api",
    "mediaproxy",
    "stator",
    "users",
]

MIDDLEWARE = [
    "core.middleware.SentryTaggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "core.middleware.HeadersMiddleware",
    "core.middleware.ConfigLoadingMiddleware",
    "api.middleware.ApiTokenMiddleware",
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

if SETUP.DATABASE_SERVER:
    DATABASES = {
        "default": dj_database_url.parse(SETUP.DATABASE_SERVER, conn_max_age=600)
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": SETUP.PGHOST,
            "PORT": SETUP.PGPORT,
            "NAME": SETUP.PGNAME,
            "USER": SETUP.PGUSER,
            "PASSWORD": SETUP.PGPASSWORD,
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

STATICFILES_DIRS = [BASE_DIR / "static"]

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

WHITENOISE_MAX_AGE = 3600

STATIC_ROOT = BASE_DIR / "static-collected"

ALLOWED_HOSTS = SETUP.ALLOWED_HOSTS

AUTO_ADMIN_EMAIL = SETUP.AUTO_ADMIN_EMAIL

STATOR_TOKEN = SETUP.STATOR_TOKEN
STATOR_CONCURRENCY = SETUP.STATOR_CONCURRENCY
STATOR_CONCURRENCY_PER_MODEL = SETUP.STATOR_CONCURRENCY_PER_MODEL

CORS_ORIGIN_ALLOW_ALL = True  # Temporary
CORS_ORIGIN_WHITELIST = SETUP.CORS_HOSTS
CORS_ALLOW_CREDENTIALS = True
CORS_PREFLIGHT_MAX_AGE = 604800

JSONLD_MAX_SIZE = 1024 * 50  # 50 KB

CSRF_TRUSTED_ORIGINS = SETUP.CSRF_HOSTS

MEDIA_URL = SETUP.MEDIA_URL
MEDIA_ROOT = SETUP.MEDIA_ROOT
MAIN_DOMAIN = SETUP.MAIN_DOMAIN

# Debug toolbar should only be loaded at all when debug is on
if DEBUG and SETUP.DEBUG_TOOLBAR:
    INSTALLED_APPS.append("debug_toolbar")
    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": "core.middleware.show_toolbar"}
    MIDDLEWARE.insert(8, "debug_toolbar.middleware.DebugToolbarMiddleware")

if SETUP.USE_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


if SETUP.SENTRY_DSN:
    sentry_sdk.init(
        dsn=SETUP.SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
        ],
        traces_sample_rate=SETUP.SENTRY_TRACES_SAMPLE_RATE,
        sample_rate=SETUP.SENTRY_SAMPLE_RATE,
        send_default_pii=True,
        environment=SETUP.ENVIRONMENT,
    )
    sentry_sdk.set_tag("takahe.version", __version__)

SERVER_EMAIL = SETUP.EMAIL_FROM
if SETUP.EMAIL_SERVER:
    parsed = urllib.parse.urlparse(SETUP.EMAIL_SERVER)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.scheme == "console":
        EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    elif parsed.scheme == "sendgrid":
        EMAIL_HOST = "smtp.sendgrid.net"
        EMAIL_PORT = 587
        EMAIL_HOST_USER = "apikey"
        # urlparse will lowercase it
        EMAIL_HOST_PASSWORD = SETUP.EMAIL_SERVER.split("://")[1]
        EMAIL_USE_TLS = True
    elif parsed.scheme == "smtp":
        EMAIL_HOST = parsed.hostname
        EMAIL_PORT = parsed.port
        EMAIL_HOST_USER = urllib.parse.unquote(parsed.username)
        EMAIL_HOST_PASSWORD = urllib.parse.unquote(parsed.password)
        EMAIL_USE_TLS = as_bool(query.get("tls"))
        EMAIL_USE_SSL = as_bool(query.get("ssl"))
    else:
        raise ValueError("Unknown schema for EMAIL_SERVER.")


if SETUP.MEDIA_BACKEND:
    parsed = urllib.parse.urlparse(SETUP.MEDIA_BACKEND)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.scheme == "gs":
        DEFAULT_FILE_STORAGE = "core.uploads.TakaheGoogleCloudStorage"
        GS_BUCKET_NAME = parsed.path.lstrip("/")
        GS_QUERYSTRING_AUTH = False
        if parsed.hostname is not None:
            port = parsed.port or 443
            GS_CUSTOM_ENDPOINT = f"https://{parsed.hostname}:{port}"
    elif parsed.scheme == "s3":
        DEFAULT_FILE_STORAGE = "core.uploads.TakaheS3Storage"
        AWS_STORAGE_BUCKET_NAME = parsed.path.lstrip("/")
        AWS_QUERYSTRING_AUTH = False
        AWS_DEFAULT_ACL = SETUP.MEDIA_BACKEND_S3_ACL
        if parsed.username is not None:
            AWS_ACCESS_KEY_ID = parsed.username
            AWS_SECRET_ACCESS_KEY = urllib.parse.unquote(parsed.password)
        if parsed.hostname is not None:
            port = parsed.port or 443
            AWS_S3_ENDPOINT_URL = f"https://{parsed.hostname}:{port}"
        if SETUP.MEDIA_URL is not None:
            media_url_parsed = urllib.parse.urlparse(SETUP.MEDIA_URL)
            AWS_S3_CUSTOM_DOMAIN = media_url_parsed.hostname
    elif parsed.scheme == "local":
        if not (MEDIA_ROOT and MEDIA_URL):
            raise ValueError(
                "You must provide MEDIA_ROOT and MEDIA_URL for a local media backend"
            )
    else:
        raise ValueError(f"Unsupported media backend {parsed.scheme}")

CACHES = {
    "default": django_cache_url.parse(SETUP.CACHES_DEFAULT or "dummy://"),
}

if SETUP.ERROR_EMAILS:
    ADMINS = [("Admin", e) for e in SETUP.ERROR_EMAILS]

TAKAHE_USER_AGENT = (
    f"python-httpx/{httpx.__version__} "
    f"(Takahe/{__version__}; +https://{SETUP.MAIN_DOMAIN}/)"
)

if SETUP.LOCAL_SETTINGS:
    # Let any errors bubble up
    from .local_settings import *  # noqa
