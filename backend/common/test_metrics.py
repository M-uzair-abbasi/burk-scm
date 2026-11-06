from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from fulfillment.models import PackScan, PackingSession
from notifications.models import Notification
from operations.models import WorkItem
from orders.models import Channel, SalesOrder, SyncRun
from surveillance.models import PackagingRecording

User = get_user_model()


METRIC_LIMITS = {
    "METRICS_WINDOW_HOURS": 24,
    "METRICS_MAX_QUEUE_DEPTH": 100,
    "METRICS_MAX_OLDEST_DUE_SECONDS": 1_000,
    "METRICS_MAX_RETRYING_WORK": 100,
    "METRICS_MAX_FAILED_WORK": 100,
    "METRICS_MAX_SOURCE_LAG_SECONDS": 1_000,
    "METRICS_MAX_SOURCE_FAILURES": 100,
    "METRICS_MAX_NOTIFICATION_LATENCY_SECONDS": 1_000,
    "METRICS_MAX_NOTIFICATION_FAILURES": 100,
    "METRICS_MAX_SHIPMENT_BOOKING_FAILURES": 100,
    "METRICS_MAX_MEDIA_PROCESSING_SECONDS": 1_000,
    "METRICS_MAX_MEDIA_FAILURES": 100,
}


def make_order(reference="SO-METRICS"):
    return SalesOrder.objects.create(
        channel=Channel.BURK,
        external_id=reference,
        reference=reference,
        customer_name="Metrics Buyer",
    )


def record_fresh_sources(now):
    for channel in Channel.values:
        SyncRun.objects.create(
            channel=channel,
            started_at=now - timedelta(seconds=10),
            finished_at=now - timedelta(seconds=5),
            fetched=0,
            ok=True,
        )


@override_settings(**METRIC_LIMITS)
class OperationalMetricsTests(TestCase):
    def test_report_aggregates_every_required_operational_signal(self):
        from common.metrics import operational_metrics

        now = timezone.now()
        WorkItem.objects.create(
            kind="send_notification",
            key="send_notification:due",
            available_at=now - timedelta(seconds=300),
        )
        WorkItem.objects.create(
            kind="process_packaging_recording",
            key="process_packaging_recording:retry",
            status=WorkItem.Status.RETRY,
            attempts=2,
            available_at=now - timedelta(seconds=60),
        )
        WorkItem.objects.create(
            kind="book_shipment",
            key="book_shipment:failed",
            status=WorkItem.Status.FAILED,
            attempts=5,
            max_attempts=5,
            available_at=now - timedelta(seconds=100),
            completed_at=now,
        )
        for channel, lag in ((Channel.BURK, 100), (Channel.DARAZ, 200)):
            SyncRun.objects.create(
                channel=channel,
                started_at=now - timedelta(seconds=lag + 5),
                finished_at=now - timedelta(seconds=lag),
                fetched=0,
                ok=True,
            )

        order = make_order()
        session = PackingSession.objects.create(order=order)
        PackScan.objects.create(
            session=session,
            barcode="WRONG",
            result=PackScan.Result.MISMATCH,
        )
        Notification.objects.create(
            order=order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            channel=Notification.Channel.EMAIL,
            idempotency_key="metrics-acknowledged",
            status=Notification.Status.SENT,
            reference_event_at=now - timedelta(seconds=120),
            acknowledged_at=now,
        )
        Notification.objects.create(
            order=order,
            kind=Notification.Kind.SHIPMENT_TRACKING,
            channel=Notification.Channel.WHATSAPP,
            idempotency_key="metrics-failed",
            status=Notification.Status.FAILED,
            reference_event_at=now,
        )
        PackagingRecording.objects.create(
            session=session,
            status=PackagingRecording.Status.READY,
            capture_stopped_at=now - timedelta(seconds=40),
            compressed_at=now,
        )

        report = operational_metrics(now=now)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["queue"]["active"], 2)
        self.assertEqual(report["queue"]["due"], 2)
        self.assertEqual(report["queue"]["retrying"], 1)
        self.assertEqual(report["queue"]["failed"], 1)
        self.assertGreaterEqual(report["queue"]["oldest_due_age_seconds"], 299)
        self.assertEqual(report["sources"]["missing"], [])
        self.assertEqual(report["sources"]["max_lag_seconds"], 200)
        self.assertEqual(report["packing"]["mismatches_intercepted"], 1)
        self.assertEqual(report["notifications"]["acknowledged"], 1)
        self.assertEqual(report["notifications"]["failed"], 1)
        self.assertEqual(report["notifications"]["max_latency_seconds"], 120)
        self.assertEqual(report["shipments"]["booking_failures"], 1)
        self.assertEqual(report["media"]["processed"], 1)
        self.assertEqual(report["media"]["max_processing_seconds"], 40)

    def test_query_count_is_bounded_independently_of_ledger_size(self):
        from common.metrics import operational_metrics

        now = timezone.now()
        record_fresh_sources(now)
        order = make_order("SO-METRICS-BOUND")
        session = PackingSession.objects.create(order=order)
        PackScan.objects.bulk_create(
            [
                PackScan(
                    session=session,
                    barcode=f"WRONG-{index}",
                    result=PackScan.Result.MISMATCH,
                )
                for index in range(200)
            ]
        )

        with CaptureQueriesContext(connection) as queries:
            report = operational_metrics(now=now)

        self.assertEqual(report["packing"]["mismatches_intercepted"], 200)
        self.assertLessEqual(len(queries), 6, [query["sql"] for query in queries])

    @override_settings(METRICS_MAX_FAILED_WORK=0)
    def test_threshold_breach_makes_check_command_exit_nonzero(self):
        now = timezone.now()
        record_fresh_sources(now)
        WorkItem.objects.create(
            kind="send_notification",
            key="send_notification:terminal",
            status=WorkItem.Status.FAILED,
            attempts=1,
            completed_at=now,
        )
        output = StringIO()

        with self.assertRaises(SystemExit) as raised:
            call_command("check_operational_metrics", "--check", stdout=output)

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("queue.failed", output.getvalue())


@override_settings(**METRIC_LIMITS)
class OperationalMetricsPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_user(
            username="metrics-manager", role=User.Role.MANAGER
        )
        self.operator = User.objects.create_user(
            username="metrics-operator", role=User.Role.OPERATOR
        )
        record_fresh_sources(timezone.now())

    def test_metrics_endpoint_is_manager_only(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get("/api/metrics/").status_code, 403)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/metrics/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("queue", response.data)
        self.assertIn("notifications", response.data)

    def test_public_health_does_not_expose_detailed_metrics(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/health/")
        self.assertEqual(set(response.json()), {"ok", "checked_at"})

    def test_detailed_health_is_manager_only(self):
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get("/api/health/details/").status_code, 403)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/health/details/")
        self.assertIn(response.status_code, (200, 503))
        self.assertIn("components", response.data)
