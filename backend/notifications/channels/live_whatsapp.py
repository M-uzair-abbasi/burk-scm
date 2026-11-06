"""Real WhatsApp Business Cloud API channel.

Sends a signed POST to https://graph.facebook.com/{version}/{PHONE_NUMBER_ID}/messages
using WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID from settings (env-backed,
like DARAZ_* or BURK_ORDER_API_*).

Deliberately a template send, not free text: confirmed live against the real
Graph API that a free-text message only ever delivers inside an open
24-hour customer-initiated conversation window (or to a pre-verified sandbox
test number) -- a real customer who hasn't messaged Burk first never
receives it. An approved message template bypasses that window, which is
the only way this can ever actually reach a customer proactively. The three
templates below (packaging_video, shipment_tracking, review_request) have to
exist and be Meta-approved under these exact names/parameter orders before
this will send successfully -- until then, every send fails with a normal
provider error, surfaced through the existing retry/failure path like any
other outage. See whatsapp_simulated._TEMPLATES for the text these mirror.
"""

from __future__ import annotations

import requests
from django.conf import settings

from .base import NotificationChannel

GRAPH_API_VERSION = "v20.0"
REQUEST_TIMEOUT_SECONDS = 15
TEMPLATE_LANGUAGE = "en_US"

# kind -> (Meta template name, ordered payload keys feeding {{1}}, {{2}}, ...)
# "ref" is synthesized the same way whatsapp_simulated._render() does, from
# notification.order.reference -- never a literal payload key.
_TEMPLATES = {
    "packaging_video": ("packaging_video", ["ref", "video_url"]),
    "shipment_tracking": ("shipment_tracking", ["ref", "courier", "tracking_number"]),
    "review_request": ("review_request", ["ref", "review_link"]),
}


def _template_parameters(notification) -> list[dict]:
    _, keys = _TEMPLATES[notification.kind]
    values = {**notification.payload, "ref": notification.order.reference}
    return [{"type": "text", "text": str(values[key])} for key in keys]


class LiveWhatsAppChannel(NotificationChannel):
    name = "whatsapp"

    def health(self) -> dict:
        from common.integrations import missing_setting_names

        missing = missing_setting_names(
            "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"
        )
        if missing:
            return {
                "ok": False,
                "mode": "live",
                "adapter": self.name,
                "missing_settings": missing,
                "detail": "missing_configuration",
            }
        # A cheap read of the phone number resource itself -- confirms the
        # token is valid and the phone number ID is reachable, without
        # sending a message or spending any send quota.
        try:
            response = requests.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
                f"{settings.WHATSAPP_PHONE_NUMBER_ID}",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
                params={"fields": "id"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - readiness result
            return {
                "ok": False,
                "mode": "live",
                "adapter": self.name,
                "error_class": exc.__class__.__name__,
            }
        return {"ok": True, "mode": "live", "adapter": self.name}

    def send(self, notification) -> dict:
        template_name, _ = _TEMPLATES[notification.kind]
        response = requests.post(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                # Meta's API wants international format without the leading
                # "+" our own normalize_country_code()-sourced numbers carry.
                "to": notification.recipient.lstrip("+"),
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": TEMPLATE_LANGUAGE},
                    "components": [
                        {
                            "type": "body",
                            "parameters": _template_parameters(notification),
                        }
                    ],
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "provider_message_id": payload["messages"][0]["id"],
            "acknowledged": True,
        }
