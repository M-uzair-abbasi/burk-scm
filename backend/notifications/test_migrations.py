from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from notifications.models import Notification
from operations.models import WorkItem
from orders.models import SalesOrder


class NotificationOutboxMigrationTests(TestCase):
    def test_backfill_creates_due_work_for_legacy_scheduled_notification(self):
        order = SalesOrder.objects.create(
            channel="burk",
            external_id="legacy-review",
            reference="SO-LEGACY-REVIEW",
            customer_email="buyer@example.invalid",
        )
        due_at = timezone.now()
        notification = Notification.objects.create(
            order=order,
            kind=Notification.Kind.REVIEW_REQUEST,
            channel=Notification.Channel.EMAIL,
            idempotency_key="legacy:review-email",
            recipient=order.customer_email,
            status=Notification.Status.SCHEDULED,
            reference_event_at=due_at,
            scheduled_for=due_at,
            payload={"review_link": "https://example.invalid/review"},
        )

        migration = import_module(
            "notifications.migrations.0004_backfill_notification_jobs"
        )
        migration.backfill_notification_jobs(apps, None)

        item = WorkItem.objects.get(key=f"send_notification:{notification.pk}")
        self.assertEqual(item.kind, "send_notification")
        self.assertEqual(item.payload, {"notification_id": notification.pk})
        self.assertEqual(item.status, WorkItem.Status.PENDING)
        self.assertEqual(item.available_at, due_at)

