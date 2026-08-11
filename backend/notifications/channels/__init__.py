"""Notification channel registry.

Mirrors orders/connectors/__init__.py: CHANNELS maps a channel key to its class.
Swapping SimulatedWhatsAppChannel for LiveWhatsAppChannel here is the only change
needed to go live for WhatsApp; EmailChannel is already real (it just points at
whatever EMAIL_BACKEND is configured).
"""

from .base import NotificationChannel
from .email_backend import EmailChannel
from .whatsapp_simulated import SimulatedWhatsAppChannel

CHANNELS = {
    "email": EmailChannel,
    "whatsapp": SimulatedWhatsAppChannel,
}

__all__ = [
    "NotificationChannel",
    "EmailChannel",
    "SimulatedWhatsAppChannel",
    "CHANNELS",
    "get_channel",
]


def get_channel(name: str) -> NotificationChannel:
    try:
        channel_cls = CHANNELS[name]
    except KeyError:
        raise ValueError(f"Unknown notification channel: {name!r}")
    return channel_cls()
