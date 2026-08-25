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
FRONTEND_ORIGIN = env("FRONTEND_ORIGIN")
PRODUCTION_MODE = env.bool("PRODUCTION_MODE", default=not DEBUG)
DEMO_ACTIONS_ENABLED = env.bool(
    "DEMO_ACTIONS_ENABLED", default=DEBUG and not PRODUCTION_MODE
)
DEMO_MODE_ENABLED = env.bool(
    "DEMO_MODE_ENABLED", default=DEBUG and not PRODUCTION_MODE
)
ORDER_CONNECTOR_BACKENDS = env.json(
    "ORDER_CONNECTOR_BACKENDS",
    default={"burk": "fixture", "daraz": "fixture"},
)
ALLOW_DEMO_RESET = env.bool("ALLOW_DEMO_RESET", default=False)
WORKER_LEASE_SECONDS = env.int("WORKER_LEASE_SECONDS", default=60)
WORKER_BACKOFF_BASE_SECONDS = env.int("WORKER_BACKOFF_BASE_SECONDS", default=5)
WORKER_BACKOFF_MAX_SECONDS = env.int("WORKER_BACKOFF_MAX_SECONDS", default=300)
NOTIFICATION_REQUIRED_CHANNELS = env.list(
    "NOTIFICATION_REQUIRED_CHANNELS", default=["email", "whatsapp"]
)
NOTIFICATION_WEBHOOK_SECRETS = env.json("NOTIFICATION_WEBHOOK_SECRETS", default={})
NOTIFICATION_WEBHOOK_MAX_BYTES = env.int(
    "NOTIFICATION_WEBHOOK_MAX_BYTES", default=65_536
)
PACKAGING_CAMERA_BACKEND = env("PACKAGING_CAMERA_BACKEND", default="simulated")
PACKAGING_CAMERA_SOURCE = env("PACKAGING_CAMERA_SOURCE", default="")
PACKAGING_PROCESS_MAX_ATTEMPTS = env.int(
    "PACKAGING_PROCESS_MAX_ATTEMPTS", default=3
)
PACKAGING_LINK_TTL_SECONDS = env.int(
    "PACKAGING_LINK_TTL_SECONDS", default=7 * 24 * 60 * 60
)
PACKAGING_RAW_RETENTION_SECONDS = env.int(
    "PACKAGING_RAW_RETENTION_SECONDS", default=24 * 60 * 60
)
PACKAGING_COMPRESSED_RETENTION_SECONDS = env.int(
    "PACKAGING_COMPRESSED_RETENTION_SECONDS", default=30 * 24 * 60 * 60
)
PUBLIC_APP_ORIGIN = env("PUBLIC_APP_ORIGIN", default=FRONTEND_ORIGIN)
COURIER_BACKEND = env("COURIER_BACKEND", default="simulated")
LEOPARD_API_KEY = env("LEOPARD_API_KEY", default="")
LEOPARD_API_PASSWORD = env("LEOPARD_API_PASSWORD", default="")
SHIPMENT_BOOKING_MAX_ATTEMPTS = env.int(
    "SHIPMENT_BOOKING_MAX_ATTEMPTS", default=5
)
COURIER_WEBHOOK_SECRETS = env.json("COURIER_WEBHOOK_SECRETS", default={})
COURIER_WEBHOOK_MAX_BYTES = env.int("COURIER_WEBHOOK_MAX_BYTES", default=65_536)
WORKER_HEARTBEAT_MAX_AGE_SECONDS = env.int(
    "WORKER_HEARTBEAT_MAX_AGE_SECONDS", default=120
)
WORK_QUEUE_MAX_DUE_AGE_SECONDS = env.int(
    "WORK_QUEUE_MAX_DUE_AGE_SECONDS", default=180
)
MEDIA_MIN_FREE_BYTES = env.int("MEDIA_MIN_FREE_BYTES", default=100 * 1024 * 1024)
REQUIRE_LIVE_INTEGRATIONS = env.bool(
    "REQUIRE_LIVE_INTEGRATIONS", default=PRODUCTION_MODE
)
METRICS_WINDOW_HOURS = env.int("METRICS_WINDOW_HOURS", default=24)
METRICS_MAX_QUEUE_DEPTH = env.int("METRICS_MAX_QUEUE_DEPTH", default=100)
METRICS_MAX_OLDEST_DUE_SECONDS = env.int(
    "METRICS_MAX_OLDEST_DUE_SECONDS", default=180
)
METRICS_MAX_RETRYING_WORK = env.int("METRICS_MAX_RETRYING_WORK", default=25)
METRICS_MAX_FAILED_WORK = env.int("METRICS_MAX_FAILED_WORK", default=0)
METRICS_MAX_SOURCE_LAG_SECONDS = env.int(
    "METRICS_MAX_SOURCE_LAG_SECONDS", default=15 * 60
)
METRICS_MAX_SOURCE_FAILURES = env.int("METRICS_MAX_SOURCE_FAILURES", default=0)
METRICS_MAX_NOTIFICATION_LATENCY_SECONDS = env.int(
    "METRICS_MAX_NOTIFICATION_LATENCY_SECONDS", default=180
)
METRICS_MAX_NOTIFICATION_FAILURES = env.int(
    "METRICS_MAX_NOTIFICATION_FAILURES", default=0
)
METRICS_MAX_SHIPMENT_BOOKING_FAILURES = env.int(
    "METRICS_MAX_SHIPMENT_BOOKING_FAILURES", default=0
)
METRICS_MAX_MEDIA_PROCESSING_SECONDS = env.int(
    "METRICS_MAX_MEDIA_PROCESSING_SECONDS", default=180
)
METRICS_MAX_MEDIA_FAILURES = env.int("METRICS_MAX_MEDIA_FAILURES", default=0)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "operations",
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
    "common.middleware.CorrelationIdMiddleware",
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
STATIC_ROOT = Path(env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))

# Private Module 4 storage (raw + FFmpeg-compressed). MEDIA_URL names the file
# namespace for storage compatibility only; config.urls intentionally exposes no
# static media route. Playback always goes through the authorized recording API.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_IP_THROTTLE_RATE = env("LOGIN_IP_THROTTLE_RATE", default="20/min")
LOGIN_ACCOUNT_THROTTLE_RATE = env("LOGIN_ACCOUNT_THROTTLE_RATE", default="5/min")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_RATES": {
        "login_ip": LOGIN_IP_THROTTLE_RATE,
        "login_account": LOGIN_ACCOUNT_THROTTLE_RATE,
    },
}

# The frontend reaches the API through Next's rewrites proxy, so the browser
# only ever sees one origin and no CORS preflight occurs. Django still needs
# the origin trusted: Next forwards the browser's Origin header, which will
# not match this server's own host, and unsafe requests would 403 without it.
CSRF_TRUSTED_ORIGINS = [FRONTEND_ORIGIN]
CSRF_TRUSTED_ORIGINS.extend(
    env.list("CSRF_TRUSTED_ORIGINS_EXTRA", default=[])
)
if DEBUG:
    CSRF_TRUSTED_ORIGINS.append("http://127.0.0.1:3001")

# localhost:3001 and localhost:8000 are different origins but the same site
# (site ignores port), so Lax cookies are delivered without needing None/Secure.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=PRODUCTION_MODE)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=PRODUCTION_MODE)
# The frontend must read this token to echo it back in the X-CSRFToken header.
CSRF_COOKIE_HTTPONLY = False

# Production transport security. TRUST_X_FORWARDED_PROTO must only be enabled
# when Django is behind a trusted reverse proxy that overwrites this header.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=PRODUCTION_MODE)
SECURE_HSTS_SECONDS = env.int(
    "SECURE_HSTS_SECONDS", default=31536000 if PRODUCTION_MODE else 0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=PRODUCTION_MODE
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=PRODUCTION_MODE)
if env.bool("TRUST_X_FORWARDED_PROTO", default=PRODUCTION_MODE):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_PROXY_SSL_HEADER = None

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
WHATSAPP_BACKEND = env("WHATSAPP_BACKEND", default="simulated")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")

# Order-source credentials are read only by live adapter slots. The fixture
# connectors never inspect them and are refused outside demo/test mode.
DARAZ_APP_KEY = env("DARAZ_APP_KEY", default="")
DARAZ_APP_SECRET = env("DARAZ_APP_SECRET", default="")
DARAZ_ACCESS_TOKEN = env("DARAZ_ACCESS_TOKEN", default="")
DARAZ_API_BASE_URL = env("DARAZ_API_BASE_URL", default="")
BURK_ORDER_API_BASE_URL = env("BURK_ORDER_API_BASE_URL", default="")
BURK_ORDER_API_TOKEN = env("BURK_ORDER_API_TOKEN", default="")

# Module 6: how long after delivery the review-reminder notification is made
# eligible for the durable worker. A real deployment normally uses hours/days.
REVIEW_REMINDER_DELAY_SECONDS = env.int("REVIEW_REMINDER_DELAY_SECONDS", default=60)
REVIEW_LINK_BACKEND = env("REVIEW_LINK_BACKEND", default="simulated")
BURK_REVIEW_BASE_URL = env(
    "BURK_REVIEW_BASE_URL", default="https://burk.pk/review"
)
BURK_REVIEW_API_BASE_URL = env("BURK_REVIEW_API_BASE_URL", default="")
BURK_REVIEW_API_TOKEN = env("BURK_REVIEW_API_TOKEN", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "common.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
