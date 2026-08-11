"""
Django settings for Burk.pk SCM-OVS.

Django 5.2 LTS. Configuration is read from ../.env via django-environ.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    FRONTEND_ORIGIN=(str, "http://localhost:3001"),
)
environ.Env.read_env(REPO_ROOT / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "common",
    "inventory",
    "suppliers",
    "purchasing",
    "orders",
    "fulfillment",
    "notifications",
    "surveillance",
    "logistics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://burk:burk@localhost:5433/burk_scm",
    ),
}

# Must be set before the first migrate. Swapping it afterwards is not
# practically recoverable without dropping the database.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Module 4: packaging-video clips (raw + ffmpeg-compressed). Gitignored
# (/backend/media/) — generated demo artifacts, not source.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# The frontend reaches the API through Next's rewrites proxy, so the browser
# only ever sees one origin and no CORS preflight occurs. Django still needs
# the origin trusted: Next forwards the browser's Origin header, which will
# not match this server's own host, and unsafe requests would 403 without it.
CSRF_TRUSTED_ORIGINS = [
    env("FRONTEND_ORIGIN"),
    "http://127.0.0.1:3001",
]

# localhost:3001 and localhost:8000 are different origins but the same site
# (site ignores port), so Lax cookies are delivered without needing None/Secure.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# The frontend must read this token to echo it back in the X-CSRFToken header.
CSRF_COOKIE_HTTPONLY = False

# Module 4/5/6: real email delivery (notifications.channels.email_backend). The
# console backend prints the message to the runserver log — nothing external is
# contacted in dev/test. Point EMAIL_BACKEND at
# django.core.mail.backends.smtp.EmailBackend and set EMAIL_HOST/EMAIL_HOST_USER/
# EMAIL_HOST_PASSWORD/EMAIL_PORT/EMAIL_USE_TLS in .env for real SMTP (SendGrid,
# Gmail, ...) with no code change.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Burk.pk <no-reply@burk.pk>")

# Module 6: how long after delivery the review-reminder notification is
# scheduled for. Short by default so the demo can show it correctly NOT firing
# immediately, then firing once dispatch_scheduled_notifications is run again
# after the delay — a real deployment would use hours/days, not seconds.
REVIEW_REMINDER_DELAY_SECONDS = env.int("REVIEW_REMINDER_DELAY_SECONDS", default=60)
