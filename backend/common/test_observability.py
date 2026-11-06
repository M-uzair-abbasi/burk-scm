import json
import logging
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from common.health import operational_health
from common.logging import JsonFormatter
from operations.models import WorkItem, WorkerHeartbeat
from operations.services import enqueue
from unittest.mock import Mock, patch


class CorrelationMiddlewareTests(TestCase):
    def test_valid_request_id_is_echoed_and_invalid_value_is_replaced(self):
        valid = "request-12345678"
        response = self.client.get("/api/health/", HTTP_X_REQUEST_ID=valid)
        self.assertEqual(response["X-Request-ID"], valid)

        replaced = self.client.get(
            "/api/health/", HTTP_X_REQUEST_ID="bad value\nforged"
        )["X-Request-ID"]
        self.assertNotEqual(replaced, "bad value\nforged")
        self.assertRegex(replaced, r"^[a-f0-9]{32}$")

    def test_json_formatter_redacts_message_pii_and_ignores_unsafe_extras(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="sent to buyer@example.test +923001234567 token=secret-value",
            args=(),
            exc_info=None,
        )
        record.event = "notification_sent"
        record.order_id = 42
        record.password = "never-log-this"
        record.raw_payload = {"customer_phone": "+923001234567"}

        rendered = JsonFormatter().format(record)
        payload = json.loads(rendered)

        self.assertEqual(payload["event"], "notification_sent")
        self.assertEqual(payload["order_id"], 42)
        self.assertNotIn("buyer@example.test", rendered)
        self.assertNotIn("+923001234567", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("never-log-this", rendered)
        self.assertNotIn("raw_payload", rendered)


@override_settings(
    PRODUCTION_MODE=False,
    DEMO_MODE_ENABLED=True,
    ORDER_CONNECTOR_BACKENDS={"burk": "fixture", "daraz": "fixture"},
    PACKAGING_CAMERA_BACKEND="simulated",
    COURIER_BACKEND="simulated",
    WHATSAPP_BACKEND="simulated",
    REVIEW_LINK_BACKEND="simulated",
    WORKER_HEARTBEAT_MAX_AGE_SECONDS=120,
    WORK_QUEUE_MAX_DUE_AGE_SECONDS=180,
    MEDIA_MIN_FREE_BYTES=0,
    REQUIRE_LIVE_INTEGRATIONS=False,
)
class OperationalHealthTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=Path(self._tmp.name))
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)
        WorkerHeartbeat.objects.create(name="health-worker")

    def test_all_required_components_report_healthy(self):
        report = operational_health()

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            set(report["components"]),
            {"app", "database", "worker", "backlog", "media", "adapters"},
        )

    def test_stale_worker_and_old_due_job_make_readiness_unhealthy(self):
        now = timezone.now()
        WorkerHeartbeat.objects.update(
            last_seen_at=now - timedelta(minutes=10)
        )
        item = enqueue("example", "health-overdue", {})
        WorkItem.objects.filter(pk=item.pk).update(
            available_at=now - timedelta(minutes=10)
        )

        report = operational_health(now=now)

        self.assertFalse(report["ok"])
        self.assertFalse(report["components"]["worker"]["ok"])
        self.assertFalse(report["components"]["backlog"]["ok"])
        self.assertEqual(report["components"]["backlog"]["due"], 1)

    def test_future_scheduled_work_does_not_degrade_backlog(self):
        enqueue(
            "example",
            "health-future",
            {},
            available_at=timezone.now() + timedelta(hours=1),
        )

        report = operational_health()

        self.assertTrue(report["components"]["backlog"]["ok"])
        self.assertEqual(report["components"]["backlog"]["due"], 0)

    def test_health_endpoint_and_check_command_return_nonzero_when_stale(self):
        WorkerHeartbeat.objects.update(
            last_seen_at=timezone.now() - timedelta(minutes=10)
        )

        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])
        with self.assertRaises(SystemExit) as raised:
            call_command("check_operational_health", "--check", stdout=StringIO())
        self.assertEqual(raised.exception.code, 1)

    def test_required_adapter_outage_returns_503_without_leaking_exception_text(self):
        camera = Mock()
        camera.health.return_value = {
            "ok": False,
            "mode": "live",
            "detail": "unavailable",
        }
        with patch("common.health.get_camera", return_value=camera):
            report = operational_health()

        self.assertFalse(report["components"]["adapters"]["ok"])

    @override_settings(
        DEMO_MODE_ENABLED=False,
        REQUIRE_LIVE_INTEGRATIONS=True,
        ORDER_CONNECTOR_BACKENDS={"burk": "live", "daraz": "live"},
        PACKAGING_CAMERA_BACKEND="browser",
        COURIER_BACKEND="live_leopard",
        WHATSAPP_BACKEND="live",
        REVIEW_LINK_BACKEND="live_burk",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.invalid",
        EMAIL_HOST_PASSWORD="smtp-super-secret",
        DARAZ_APP_KEY="daraz-key-secret",
        DARAZ_APP_SECRET="daraz-app-secret",
        DARAZ_ACCESS_TOKEN="daraz-token-secret",
        DARAZ_API_BASE_URL="https://daraz.example.invalid",
        BURK_ORDER_API_BASE_URL="https://burk.example.invalid",
        BURK_ORDER_API_CONSUMER_KEY="burk-consumer-key-secret",
        BURK_ORDER_API_CONSUMER_SECRET="burk-consumer-secret-secret",
        LEOPARD_API_KEY="leopard-key-secret",
        LEOPARD_API_PASSWORD="leopard-password-secret",
        WHATSAPP_ACCESS_TOKEN="whatsapp-token-secret",
        WHATSAPP_PHONE_NUMBER_ID="123456789",
        BURK_REVIEW_API_BASE_URL="https://burk.example.invalid/reviews",
        BURK_REVIEW_API_TOKEN="review-token-secret",
    )
    def test_readiness_lists_every_live_dependency_without_leaking_credentials(self):
        report = operational_health()
        details = report["components"]["adapters"]["details"]

        self.assertEqual(
            {item["name"] for item in details},
            {
                "camera",
                "courier",
                "notification.email",
                "notification.whatsapp",
                "orders.burk",
                "orders.daraz",
                "review",
            },
        )
        self.assertFalse(report["components"]["adapters"]["ok"])
        serialized = json.dumps(details)
        for secret in (
            "smtp-super-secret",
            "daraz-app-secret",
            "daraz-token-secret",
            "burk-token-secret",
            "leopard-password-secret",
            "whatsapp-token-secret",
            "review-token-secret",
        ):
            self.assertNotIn(secret, serialized)
