"""Shared safety helpers for external-integration adapter registries."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def require_demo_mode(adapter_label: str) -> None:
    """Prevent fixture/simulated transports from running outside demo/test."""
    if settings.PRODUCTION_MODE or not settings.DEMO_MODE_ENABLED:
        raise ImproperlyConfigured(
            f"{adapter_label} is simulated and is disabled outside demo/test mode."
        )


def missing_setting_names(*names: str) -> list[str]:
    return [name for name in names if not getattr(settings, name, "")]


def pending_live_health(adapter: str, *required_settings: str) -> dict:
    """Truthful health for a live slot whose provider contract is still blocked."""
    missing = missing_setting_names(*required_settings)
    return {
        "ok": False,
        "mode": "live",
        "adapter": adapter,
        "missing_settings": missing,
        "detail": "missing_configuration" if missing else "implementation_pending",
    }
