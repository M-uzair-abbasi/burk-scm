"""Placeholder for the real WhatsApp Business Cloud API channel.

The documented drop-in for production, same role as orders/connectors/live_daraz.py.
To activate: implement send() as a signed POST to
https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages with the message
text/template, provide WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID via
settings (env-backed, like DARAZ_* would be), and register this class instead of
SimulatedWhatsAppChannel in channels/__init__.py. normalize()-equivalent message
rendering is inherited from nowhere here on purpose — reuse
whatsapp_simulated._render so the two channels stay message-for-message identical.
"""

from __future__ import annotations

from .base import NotificationChannel


class LiveWhatsAppChannel(NotificationChannel):
    name = "whatsapp"

    def send(self, notification) -> dict:
        raise NotImplementedError(
            "Live WhatsApp Cloud API integration requires WHATSAPP_ACCESS_TOKEN "
            "and WHATSAPP_PHONE_NUMBER_ID. Implement the signed Graph API POST here."
        )
