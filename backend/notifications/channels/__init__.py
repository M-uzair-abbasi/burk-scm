"""Environment-selected customer-notification channel registry."""

from django.conf import settings

from common.integrations import require_demo_mode

from .base import NotificationChannel
from .email_backend import EmailChannel
from .whatsapp_simulated import SimulatedWhatsAppChannel
from .live_whatsapp import LiveWhatsAppChannel

CHANNELS = {
    "email": EmailChannel,
}
WHATSAPP_CHANNELS = {
    "simulated": SimulatedWhatsAppChannel,
    "live": LiveWhatsAppChannel,
}

__all__ = [
    "NotificationChannel",
    "EmailChannel",
    "SimulatedWhatsAppChannel",
    "LiveWhatsAppChannel",
    "CHANNELS",
    "WHATSAPP_CHANNELS",
    "get_channel",
]


def get_channel(name: str) -> NotificationChannel:
    if name == "email":
        channel = EmailChannel()
        if channel.health().get("mode") == "simulated":
            require_demo_mode("notification.email")
        return channel
    if name == "whatsapp":
        backend = settings.WHATSAPP_BACKEND
        if backend == "simulated":
            require_demo_mode("notification.whatsapp")
        try:
            return WHATSAPP_CHANNELS[backend]()
        except KeyError as exc:
            raise ValueError(f"Unknown WhatsApp backend: {backend!r}") from exc
    try:
        channel_cls = CHANNELS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown notification channel: {name!r}") from exc
    return channel_cls()
