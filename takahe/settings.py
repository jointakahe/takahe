import os
import secrets
import sys
import urllib.parse
from pathlib import Path
from typing import List, Literal, Optional, Union

import dj_database_url
import sentry_sdk
from pydantic import AnyUrl, BaseSettings, EmailStr, Field, validator
from sentry_sdk.integrations.django import DjangoIntegration

BASE_DIR = Path(__file__).resolve().parent.parent


class ImplicitHostname(AnyUrl):
    host_required = False


class MediaBackendUrl(AnyUrl):
    host_required = False
    allowed_schemes = {"s3", "gcs", "local"}


def as_bool(v: Optional[Union[str, List[str]]]):
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
    DATABASE_SERVER: Optional[ImplicitHostname]

    #: The currently running environment, used for things such as sentry
    #: error reporting.
    ENVIRONMENT: Environments = "development"

    #: Should django run in debug mode?
    DEBUG: bool = False

    #: Set a secret key used for signing values such as sessions. Randomized
    #: by default, so you'll logout everytime the process restarts.
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_hex(128))

    #: Set a secret key used to protect the stator. Randomized by default.
    STATOR_TOKEN: str = Field(default_factory=lambda: secrets.token_hex(128))

    #: If set, a list of allowed values for the HOST header. The default value
    #: of '*' means any host will be accepted.
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["*"])

    #: If set, a list of hosts to accept for CORS.
    CORS_HOSTS: List[str] = Field(default_factory=list)

    #: If set, a list of hosts to accept for CSRF.
    CSRF_HOSTS: List[str] = Field(default_factory=list)

    #: If enabled, trust the HTTP_X_FORWARDED_FOR header.
    USE_PROXY_HEADERS: bool = False

    #: An optional Sentry DSN for error reporting.
    SENTRY_DSN: Optional[str] = None

    #: Fallback domain for links.
    MAIN_DOMAIN: str = "example.com"

    EMAIL_SERVER: AnyUrl = "console://localhost"
    EMAIL_FROM: EmailStr = "test@example.com"
    AUTO_ADMIN_EMAIL: Optional[EmailStr] = None
    ERROR_EMAILS: Optional[List[EmailStr]] = None

    MEDIA_URL: str = "/media/"
    MEDIA_ROOT: str = str(BASE_DIR / "media")
    MEDIA_BACKEND: Optional[MediaBackendUrl] = None

    #: Request timeouts to use when talking to other servers Either
    #: float or tuple of floats for (connect, read, write, pool)
    REMOTE_TIMEOUT: float | tuple[float, float, float, float] = 5.0

    #: If search features like full text search should be enabled.
    #: (placeholder setting, no effect)
    SEARCH: bool = True

    PGHOST: Optional[str] = None
    PGPORT: Optional[int] = 5432
    PGNAME: str = "takahe"
    PGUSER: str = "postgres"
    PGPASSWORD: Optional[str] = None

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
    "django_htmx",
    "core",
    "activities",
    "users",
    "stator",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

if SETUP.DATABASE_SERVER:
    DATABASES = {
        "default": dj_database_url.parse(SETUP.DATABASE_SERVER, conn_max_age=600)
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql_psycopg2",
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

STATIC_ROOT = BASE_DIR / "static-collected"

ALLOWED_HOSTS = SETUP.ALLOWED_HOSTS

AUTO_ADMIN_EMAIL = SETUP.AUTO_ADMIN_EMAIL

STATOR_TOKEN = SETUP.STATOR_TOKEN

CORS_ORIGIN_WHITELIST = SETUP.CORS_HOSTS
CORS_ALLOW_CREDENTIALS = True
CORS_PREFLIGHT_MAX_AGE = 604800

CSRF_TRUSTED_ORIGINS = SETUP.CSRF_HOSTS

MEDIA_URL = SETUP.MEDIA_URL
MEDIA_ROOT = SETUP.MEDIA_ROOT
MAIN_DOMAIN = SETUP.MAIN_DOMAIN

if SETUP.USE_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


if SETUP.SENTRY_DSN:
    sentry_sdk.init(
        dsn=SETUP.SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
        ],
        traces_sample_rate=1.0,
        send_default_pii=True,
        environment=SETUP.ENVIRONMENT,
    )

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
    if parsed.scheme == "gcs":
        DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
        if parsed.path.lstrip("/"):
            GS_BUCKET_NAME = parsed.path.lstrip("/")
        else:
            GS_BUCKET_NAME = parsed.hostname
        GS_QUERYSTRING_AUTH = False
    elif parsed.scheme == "s3":
        DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
        AWS_STORAGE_BUCKET_NAME = parsed.path.lstrip("/")
        AWS_QUERYSTRING_AUTH = False
        AWS_DEFAULT_ACL = "public-read"
        if parsed.username is not None:
            AWS_ACCESS_KEY_ID = parsed.username
            AWS_SECRET_ACCESS_KEY = urllib.parse.unquote(parsed.password)
        if parsed.hostname is not None:
            port = parsed.port or 443
            AWS_S3_ENDPOINT_URL = f"https://{parsed.hostname}:{port}"
    elif parsed.scheme == "local":
        if not (MEDIA_ROOT and MEDIA_URL):
            raise ValueError(
                "You must provide MEDIA_ROOT and MEDIA_URL for a local media backend"
            )
    else:
        raise ValueError(f"Unsupported media backend {parsed.scheme}")

if SETUP.ERROR_EMAILS:
    ADMINS = [("Admin", e) for e in SETUP.ERROR_EMAILS]
