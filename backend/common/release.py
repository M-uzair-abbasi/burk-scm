"""Pure configuration checks that must pass before a live release."""

from django.conf import settings


SIMULATED_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
}
PLACEHOLDER_MARKERS = ("replace", "change-me", "example.invalid", "your-")


def _configured(name: str) -> bool:
    value = getattr(settings, name, "")
    if not isinstance(value, str) or not value.strip():
        return False
    lowered = value.lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def release_configuration_violations() -> list[str]:
    """Return setting names/contracts only—never secret values."""
    violations = []
    if not settings.PRODUCTION_MODE:
        violations.append("PRODUCTION_MODE must be True.")
    if settings.DEBUG:
        violations.append("DEBUG must be False.")
    for name in ("DEMO_MODE_ENABLED", "DEMO_ACTIONS_ENABLED", "ALLOW_DEMO_RESET"):
        if getattr(settings, name):
            violations.append(f"{name} must be False.")
    if not settings.REQUIRE_LIVE_INTEGRATIONS:
        violations.append("REQUIRE_LIVE_INTEGRATIONS must be True.")

    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if engine != "django.db.backends.postgresql":
        violations.append("DATABASES.default must use django.db.backends.postgresql.")
    if len(settings.SECRET_KEY) < 50 or settings.SECRET_KEY.startswith("django-insecure-"):
        violations.append("SECRET_KEY must be a strong environment-only value.")
    if not settings.ALLOWED_HOSTS or any(
        host in {"*", "localhost", "127.0.0.1"} for host in settings.ALLOWED_HOSTS
    ):
        violations.append("ALLOWED_HOSTS must contain only approved public hosts.")
    for name in ("FRONTEND_ORIGIN", "PUBLIC_APP_ORIGIN"):
        if not str(getattr(settings, name, "")).startswith("https://"):
            violations.append(f"{name} must use HTTPS.")

    expected_orders = {"burk": "live", "daraz": "live"}
    for channel, expected in expected_orders.items():
        if settings.ORDER_CONNECTOR_BACKENDS.get(channel) != expected:
            violations.append(f"orders.{channel} must select the live adapter.")
    if settings.PACKAGING_CAMERA_BACKEND != "live":
        violations.append("camera must select the live adapter.")
    if settings.COURIER_BACKEND != "live_leopard":
        violations.append("courier must select live_leopard.")
    if settings.WHATSAPP_BACKEND != "live":
        violations.append("WhatsApp must select the live adapter.")
    if settings.REVIEW_LINK_BACKEND != "live_burk":
        violations.append("review must select live_burk.")
    if settings.EMAIL_BACKEND in SIMULATED_EMAIL_BACKENDS:
        violations.append("EMAIL_BACKEND must select a live transport.")

    required_names = (
        "EMAIL_HOST",
        "DARAZ_APP_KEY",
        "DARAZ_APP_SECRET",
        "DARAZ_ACCESS_TOKEN",
        "DARAZ_API_BASE_URL",
        "BURK_ORDER_API_BASE_URL",
        "BURK_ORDER_API_CONSUMER_KEY",
        "BURK_ORDER_API_CONSUMER_SECRET",
        "PACKAGING_CAMERA_SOURCE",
        "LEOPARD_API_KEY",
        "LEOPARD_API_PASSWORD",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "BURK_REVIEW_API_BASE_URL",
        "BURK_REVIEW_API_TOKEN",
    )
    for name in required_names:
        if not _configured(name):
            violations.append(f"{name} is missing or still a placeholder.")
    if not settings.COURIER_WEBHOOK_SECRETS.get("leopard"):
        violations.append("COURIER_WEBHOOK_SECRETS.leopard is required.")
    if not settings.NOTIFICATION_WEBHOOK_SECRETS.get("whatsapp"):
        violations.append("NOTIFICATION_WEBHOOK_SECRETS.whatsapp is required.")
    return violations
