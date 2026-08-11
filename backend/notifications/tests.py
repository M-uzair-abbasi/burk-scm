"""Notification dispatch tests — the KPI #2 latency mechanics in isolation from
any specific module, plus the scheduled-send sweep Module 6 relies on."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from orders.models import SalesOrder
from notifications.models import Notification
from notifications.services import dispatch, dispatch_due_scheduled, latency_report


def make_order(ref="SO-N0001", email="buyer@example.invalid", phone="+923001112222"):
    return SalesOrder.objects.create(
        channel="burk",
        external_id=ref,
        reference=ref,
        status="packed",
        customer_name="Test Buyer",
        customer_email=email,
        customer_phone=phone,
    )


class DispatchTests(TestCase):
    def test_dispatch_creates_one_notification_per_channel_and_sends_immediately(self):
        order = make_order()
        now = timezone.now()
        created = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=now,
            payload={"video_url": "https://example.invalid/v.mp4"},
        )
        self.assertEqual(len(created), 2)
        channels = {n.channel for n in created}
        self.assertEqual(channels, {"email", "whatsapp"})
        for n in created:
            self.assertEqual(n.status, Notification.Status.SENT)
            self.assertIsNotNone(n.sent_at)
            self.assertIsNotNone(n.latency_seconds)
            self.assertLess(n.latency_seconds, 5)  # well under the 180s KPI budget

    def test_dispatch_resolves_recipient_from_order(self):
        order = make_order(email="specific@example.invalid", phone="+923339990000")
        created = dispatch(
            order,
            kind=Notification.Kind.SHIPMENT_TRACKING,
            reference_event_at=timezone.now(),
            payload={"courier": "leopard", "tracking_number": "LP123456789"},
        )
        by_channel = {n.channel: n for n in created}
        self.assertEqual(by_channel["email"].recipient, "specific@example.invalid")
        self.assertEqual(by_channel["whatsapp"].recipient, "+923339990000")

    def test_missing_recipient_fails_that_channel_without_raising(self):
        order = make_order(email="", phone="")
        created = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/v.mp4"},
        )
        for n in created:
            self.assertEqual(n.status, Notification.Status.FAILED)
            self.assertTrue(n.error)

    def test_future_scheduled_for_does_not_send_immediately(self):
        order = make_order()
        future = timezone.now() + timedelta(minutes=5)
        created = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "https://example.invalid/review/SO-N0001"},
            scheduled_for=future,
        )
        for n in created:
            self.assertEqual(n.status, Notification.Status.SCHEDULED)
            self.assertIsNone(n.sent_at)

    def test_dispatch_due_scheduled_sends_only_what_is_due(self):
        order = make_order()
        future = timezone.now() + timedelta(minutes=5)
        due = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=future,
        )
        not_due = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=future,
        )
        # Fast-forward only the first batch's due time into the past, as if the
        # scheduler tick arrived after the wait — dispatch() itself would have
        # sent a past scheduled_for immediately, which isn't what this test is
        # exercising (that's covered by test_future_scheduled_for_does_not_send_immediately).
        Notification.objects.filter(id__in=[n.id for n in due]).update(
            scheduled_for=timezone.now() - timedelta(minutes=1)
        )
        sent = dispatch_due_scheduled()
        sent_ids = {n.id for n in sent}
        self.assertEqual(sent_ids, {n.id for n in due})
        for n in not_due:
            n.refresh_from_db()
            self.assertEqual(n.status, Notification.Status.SCHEDULED)


class LatencyReportTests(TestCase):
    def test_report_flags_breach_over_threshold(self):
        order = make_order()
        old_reference = timezone.now() - timedelta(seconds=400)
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=old_reference,
            payload={"video_url": "x"},
        )
        report = latency_report(Notification.Kind.PACKAGING_VIDEO, threshold_seconds=180)
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["breaches"]), 2)  # email + whatsapp both breach

    def test_report_ok_when_within_threshold(self):
        order = make_order()
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "x"},
        )
        report = latency_report(Notification.Kind.PACKAGING_VIDEO, threshold_seconds=180)
        self.assertTrue(report["ok"])

    def test_report_flags_a_scheduled_notification_past_its_own_due_time(self):
        # dispatch_scheduled_notifications was never run past scheduled_for —
        # the missed-cron-tick case latency_report's "stuck" count exists to catch.
        order = make_order()
        overdue = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=timezone.now() + timedelta(minutes=5),
        )
        Notification.objects.filter(id__in=[n.id for n in overdue]).update(
            scheduled_for=timezone.now() - timedelta(minutes=1)
        )
        report = latency_report(Notification.Kind.REVIEW_REQUEST)
        self.assertFalse(report["ok"])
        self.assertEqual(report["stuck"], 2)

    def test_report_does_not_flag_a_notification_still_waiting_on_time(self):
        order = make_order()
        dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=timezone.now() + timedelta(minutes=5),
        )
        report = latency_report(Notification.Kind.REVIEW_REQUEST)
        self.assertTrue(report["ok"])
        self.assertEqual(report["stuck"], 0)
