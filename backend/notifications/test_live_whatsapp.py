"""Tests for the live WhatsApp Cloud API channel, against mocked HTTP
responses shaped like the real Graph API (verified by hand against a real
send and a real hello_world template delivery before writing this)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from .channels.live_whatsapp import LiveWhatsAppChannel

LIVE_SETTINGS = dict(
    WHATSAPP_ACCESS_TOKEN="test-token",
    WHATSAPP_PHONE_NUMBER_ID="1475720445626497",
)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


def _notification(kind: str, payload: dict, recipient="+923432499245") -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        order=SimpleNamespace(reference="SO-00123"),
        payload=payload,
        recipient=recipient,
    )


@override_settings(**LIVE_SETTINGS)
class HealthTests(TestCase):
    @override_settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
    def test_health_names_missing_settings(self):
        health = LiveWhatsAppChannel().health()

        self.assertFalse(health["ok"])
        self.assertEqual(
            set(health["missing_settings"]),
            {"WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"},
        )

    @patch("notifications.channels.live_whatsapp.requests.get")
    def test_health_pings_the_phone_number_resource(self, mock_get):
        mock_get.return_value = _FakeResponse({"id": "1475720445626497"})

        health = LiveWhatsAppChannel().health()

        self.assertTrue(health["ok"])
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn("1475720445626497", mock_get.call_args.args[0])

    @patch("notifications.channels.live_whatsapp.requests.get")
    def test_health_reports_an_invalid_token(self, mock_get):
        mock_get.return_value = _FakeResponse({"error": "bad token"}, status=401)

        health = LiveWhatsAppChannel().health()

        self.assertFalse(health["ok"])
        self.assertEqual(health["error_class"], "HTTPError")


@override_settings(**LIVE_SETTINGS)
class SendTests(TestCase):
    @patch("notifications.channels.live_whatsapp.requests.post")
    def test_sends_packaging_video_as_a_template_with_ordered_parameters(
        self, mock_post
    ):
        mock_post.return_value = _FakeResponse(
            {"messages": [{"id": "wamid.ABC123"}]}
        )
        notification = _notification(
            "packaging_video", {"video_url": "https://scm.burk.pk/v/abc"}
        )

        result = LiveWhatsAppChannel().send(notification)

        self.assertEqual(
            result, {"provider_message_id": "wamid.ABC123", "acknowledged": True}
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["type"], "template")
        self.assertEqual(body["template"]["name"], "packaging_video")
        self.assertEqual(
            body["template"]["components"][0]["parameters"],
            [
                {"type": "text", "text": "SO-00123"},
                {"type": "text", "text": "https://scm.burk.pk/v/abc"},
            ],
        )

    @patch("notifications.channels.live_whatsapp.requests.post")
    def test_sends_shipment_tracking_with_its_three_parameters_in_order(
        self, mock_post
    ):
        mock_post.return_value = _FakeResponse(
            {"messages": [{"id": "wamid.DEF456"}]}
        )
        notification = _notification(
            "shipment_tracking",
            {"courier": "leopard", "tracking_number": "LC-998877"},
        )

        LiveWhatsAppChannel().send(notification)

        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["template"]["name"], "shipment_tracking")
        self.assertEqual(
            body["template"]["components"][0]["parameters"],
            [
                {"type": "text", "text": "SO-00123"},
                {"type": "text", "text": "leopard"},
                {"type": "text", "text": "LC-998877"},
            ],
        )

    @patch("notifications.channels.live_whatsapp.requests.post")
    def test_strips_the_leading_plus_from_the_recipient(self, mock_post):
        mock_post.return_value = _FakeResponse(
            {"messages": [{"id": "wamid.GHI789"}]}
        )
        notification = _notification(
            "review_request", {"review_link": "https://burk.pk/r/1"}
        )

        LiveWhatsAppChannel().send(notification)

        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["to"], "923432499245")

    @patch("notifications.channels.live_whatsapp.requests.post")
    def test_an_unapproved_template_surfaces_as_an_ordinary_provider_error(
        self, mock_post
    ):
        mock_post.return_value = _FakeResponse(
            {"error": {"message": "Template name does not exist"}}, status=400
        )
        notification = _notification(
            "review_request", {"review_link": "https://burk.pk/r/1"}
        )

        with self.assertRaises(Exception):
            LiveWhatsAppChannel().send(notification)
