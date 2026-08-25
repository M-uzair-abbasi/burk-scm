"""Simulated WhatsApp Business Cloud API channel.

No WhatsApp/Twilio credentials exist in this environment (same situation as the
simulated Daraz feed and simulated courier booking), so this channel doesn't call
out to a real provider. It reproduces the shape a real send would have — a
provider message id, a delivery status — so the Notification ledger and the
KPI #2 latency proof are indistinguishable from a real integration; only the
transport is swapped. live_whatsapp.py is the documented drop-in for production.
"""

from __future__ import annotations

import hashlib
import logging

from .base import NotificationChannel

logger = logging.getLogger("notifications.whatsapp")

_TEMPLATES = {
    "packaging_video": "Your Burk.pk order {ref} has been packed — watch it here: {video_url}",
    "shipment_tracking": "Your Burk.pk order {ref} shipped via {courier}. Tracking: {tracking_number}",
    "review_request": "How was your Burk.pk order {ref}? Leave a review: {review_link}",
}


def _render(notification) -> str:
    template = _TEMPLATES[notification.kind]
    # order.reference always wins over anything a payload might (now or in the
    # future) also store under "ref" — avoids a duplicate-keyword TypeError.
    return template.format(**{**notification.payload, "ref": notification.order.reference})


class SimulatedWhatsAppChannel(NotificationChannel):
    name = "whatsapp"

    def health(self) -> dict:
        return {"ok": True, "mode": "simulated", "adapter": self.name}

    def send(self, notification) -> dict:
        if not notification.recipient:
            raise ValueError("Order has no customer_phone on file.")
        message = _render(notification)
        provider_id = "wamid.simulated." + hashlib.sha256(
            notification.idempotency_key.encode("utf-8")
        ).hexdigest()[:20]
        # Stands in for the provider's webhook confirmation — logged, not just
        # silently dropped, so a demo can `tail` the server log and see it land.
        logger.info(
            "notification_provider_accepted",
            extra={
                "event": "notification_provider_accepted",
                "notification_id": notification.pk,
                "order_id": notification.order_id,
                "status": "accepted",
            },
        )
        return {
            "provider_message_id": provider_id,
            "text": message,
            "simulated": True,
            "acknowledged": True,
        }
