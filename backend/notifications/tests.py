"""Notification dispatch tests — the KPI #2 latency mechanics in isolation from
any specific module, plus the scheduled-send sweep Module 6 relies on."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import SalesOrder
from notifications.models import Notification, NotificationDeliveryEvent
from notifications.reviews import get_review_link_provider
from notifications.services import dispatch, dispatch_due_scheduled, latency_report
from operations.models import WorkItem
from operations.services import process_due


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
    def test_dispatch_creates_one_notification_per_channel_then_worker_sends(self):
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
        self.assertTrue(
            all(n.status == Notification.Status.SCHEDULED for n in created)
        )

        process_due(limit=10)

        for n in created:
            n.refresh_from_db()
            self.assertEqual(n.status, Notification.Status.SENT)
            self.assertIsNotNone(n.sent_at)
            self.assertIsNotNone(n.acknowledged_at)
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
        process_due(limit=10)
        for n in created:
            n.refresh_from_db()
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
        now = timezone.now()
        due_at = now + timedelta(minutes=1)
        later = now + timedelta(minutes=10)
        due = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=due_at,
            event_key="due-review",
        )
        not_due = dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=later,
            event_key="later-review",
        )
        sent = dispatch_due_scheduled(now=now + timedelta(minutes=5))
        sent_ids = {n.id for n in sent}
        self.assertEqual(sent_ids, {n.id for n in due})
        for n in due:
            n.refresh_from_db()
            self.assertEqual(n.status, Notification.Status.SENT)
        for n in not_due:
            n.refresh_from_db()
            self.assertEqual(n.status, Notification.Status.SCHEDULED)


class LatencyReportTests(TestCase):
    def test_report_fails_without_sent_evidence(self):
        report = latency_report(
            Notification.Kind.PACKAGING_VIDEO,
            threshold_seconds=180,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report.get("evidence_count"), 0)

    def test_report_fails_when_required_channels_failed(self):
        order = make_order(email="", phone="")
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "x"},
        )
        process_due(limit=10)

        report = latency_report(
            Notification.Kind.PACKAGING_VIDEO,
            threshold_seconds=180,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["failed"], 2)
        self.assertEqual(len(report.get("failed_detail", [])), 2)

    def test_report_flags_breach_over_threshold(self):
        order = make_order()
        old_reference = timezone.now() - timedelta(seconds=400)
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=old_reference,
            payload={"video_url": "x"},
        )
        process_due(limit=10)
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
        process_due(limit=10)
        report = latency_report(Notification.Kind.PACKAGING_VIDEO, threshold_seconds=180)
        self.assertTrue(report["ok"])

    def test_report_requires_every_configured_packaging_channel(self):
        order = make_order()
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "x"},
            channels=(Notification.Channel.EMAIL,),
        )
        process_due(limit=10)

        report = latency_report(Notification.Kind.PACKAGING_VIDEO)

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["missing_required_channels"][0]["channels"], ["whatsapp"]
        )

    def test_report_rejects_sent_row_without_acknowledgement(self):
        order = make_order()
        created = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "x"},
        )
        process_due(limit=10)
        Notification.objects.filter(pk=created[0].pk).update(acknowledged_at=None)

        report = latency_report(Notification.Kind.PACKAGING_VIDEO)

        self.assertFalse(report["ok"])
        self.assertEqual(report["pending"], 1)

    def test_report_flags_a_scheduled_notification_past_its_own_due_time(self):
        # The worker never drained an already-due scheduled event.
        order = make_order()
        dispatch(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=timezone.now(),
            payload={"review_link": "x"},
            scheduled_for=timezone.now() - timedelta(minutes=1),
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


class DispatchLatencyCommandTests(TestCase):
    def test_check_exits_nonzero_without_packaging_video_evidence(self):
        with self.assertRaises(SystemExit) as raised:
            call_command("check_dispatch_latency", "--check")

        self.assertEqual(raised.exception.code, 1)

    def test_check_exits_nonzero_when_packaging_video_channels_failed(self):
        order = make_order(email="", phone="")
        dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "x"},
        )
        process_due(limit=10)

        with self.assertRaises(SystemExit) as raised:
            call_command("check_dispatch_latency", "--check")

        self.assertEqual(raised.exception.code, 1)


class DurableOutboxTests(TestCase):
    def test_dispatch_persists_and_enqueues_without_sending_in_request(self):
        order = make_order(ref="SO-OUTBOX-QUEUED")
        channel = Mock()

        with patch("notifications.services.get_channel", return_value=channel):
            created = dispatch(
                order,
                kind=Notification.Kind.PACKAGING_VIDEO,
                reference_event_at=timezone.now(),
                payload={"video_url": "https://example.invalid/signed"},
            )

        self.assertEqual(len(created), 2)
        self.assertTrue(
            all(row.status == Notification.Status.SCHEDULED for row in created)
        )
        self.assertEqual(WorkItem.objects.filter(kind="send_notification").count(), 2)
        channel.send.assert_not_called()

    def test_replaying_same_event_is_idempotent_per_channel(self):
        order = make_order(ref="SO-OUTBOX-IDEMPOTENT")
        reference = timezone.now()
        first = dispatch(
            order,
            kind=Notification.Kind.SHIPMENT_TRACKING,
            reference_event_at=reference,
            payload={"tracking_number": "TRACK-1", "courier": "tcs"},
        )
        second = dispatch(
            order,
            kind=Notification.Kind.SHIPMENT_TRACKING,
            reference_event_at=reference,
            payload={"tracking_number": "TRACK-1", "courier": "tcs"},
        )

        self.assertEqual([row.id for row in first], [row.id for row in second])
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(WorkItem.objects.filter(kind="send_notification").count(), 2)

    def test_retryable_provider_failure_then_success_sends_once(self):
        order = make_order(ref="SO-OUTBOX-RETRY")
        notification = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
            channels=(Notification.Channel.EMAIL,),
            max_attempts=3,
        )[0]
        channel = Mock()
        channel.send.side_effect = [
            RuntimeError("provider unavailable"),
            {"provider_message_id": "provider-123"},
        ]

        with patch("notifications.services.get_channel", return_value=channel):
            process_due(limit=1)
            notification.refresh_from_db()
            self.assertEqual(notification.status, Notification.Status.RETRYING)
            self.assertEqual(notification.attempt_count, 1)

            WorkItem.objects.filter(kind="send_notification").update(
                available_at=timezone.now()
            )
            process_due(limit=1)

        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.attempt_count, 2)
        self.assertEqual(notification.provider_message_id, "provider-123")
        self.assertIsNotNone(notification.acknowledged_at)
        self.assertEqual(channel.send.call_count, 2)

    def test_missing_recipient_is_terminal_without_retry(self):
        order = make_order(ref="SO-OUTBOX-NO-RECIPIENT", email="", phone="")
        created = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
        )

        process_due(limit=10)

        for notification in created:
            notification.refresh_from_db()
            self.assertEqual(notification.status, Notification.Status.FAILED)
            self.assertEqual(notification.attempt_count, 1)
        self.assertFalse(WorkItem.objects.filter(status=WorkItem.Status.RETRY).exists())

    def test_unacknowledged_acceptance_requires_a_provider_message_id(self):
        order = make_order(ref="SO-OUTBOX-NO-PROVIDER-ID")
        notification = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
            channels=(Notification.Channel.WHATSAPP,),
            max_attempts=1,
        )[0]
        channel = Mock()
        channel.send.return_value = {"acknowledged": False}

        with patch("notifications.services.get_channel", return_value=channel):
            process_due(limit=1)

        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.FAILED)
        self.assertEqual(notification.terminal_error_class, "ProviderContractError")
        self.assertIsNone(notification.acknowledged_at)

    def test_adapter_result_requires_a_boolean_acknowledgement(self):
        order = make_order(ref="SO-OUTBOX-BAD-ACK")
        notification = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
            channels=(Notification.Channel.WHATSAPP,),
            max_attempts=1,
        )[0]
        channel = Mock()
        channel.send.return_value = {
            "provider_message_id": "provider-bad-ack",
            "acknowledged": "false",
        }

        with patch("notifications.services.get_channel", return_value=channel):
            process_due(limit=1)

        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.FAILED)
        self.assertEqual(notification.terminal_error_class, "ProviderContractError")

    def test_provider_detail_is_redacted_before_it_is_persisted(self):
        order = make_order(ref="SO-OUTBOX-REDACT")
        notification = dispatch(
            order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
            channels=(Notification.Channel.WHATSAPP,),
        )[0]
        channel = Mock()
        channel.send.return_value = {
            "provider_message_id": "provider-redacted",
            "acknowledged": True,
            "access_token": "must-not-persist",
            "recipient_phone": "+923001112222",
        }

        with patch("notifications.services.get_channel", return_value=channel):
            process_due(limit=1)

        notification.refresh_from_db()
        self.assertNotIn("must-not-persist", str(notification.payload))
        self.assertNotIn("+923001112222", str(notification.payload))


@override_settings(
    NOTIFICATION_WEBHOOK_SECRETS={"whatsapp": "notification-receipt-secret"},
    NOTIFICATION_REQUIRED_CHANNELS=("whatsapp",),
)
class NotificationDeliveryReceiptTests(TestCase):
    def setUp(self):
        self.order = make_order(ref="SO-RECEIPT")
        self.notification = dispatch(
            self.order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=timezone.now(),
            payload={"video_url": "https://example.invalid/signed"},
            channels=(Notification.Channel.WHATSAPP,),
        )[0]
        channel = Mock()
        channel.send.return_value = {
            "provider_message_id": "wamid-provider-1",
            "acknowledged": False,
        }
        with patch("notifications.services.get_channel", return_value=channel):
            process_due(limit=1)
        self.notification.refresh_from_db()
        self.url = "/api/notification-webhooks/whatsapp/"

    def _post(self, payload, *, secret="notification-receipt-secret"):
        body = json.dumps(payload, separators=(",", ":")).encode()
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_NOTIFICATION_SIGNATURE=f"sha256={digest}",
        )

    def _payload(self, *, event_id="receipt-1", status="delivered"):
        return {
            "event_id": event_id,
            "provider_message_id": "wamid-provider-1",
            "status": status,
            "phone": "+923001112222",
            "access_token": "must-not-be-stored",
        }

    def test_provider_acceptance_waits_for_delivery_acknowledgement(self):
        self.assertEqual(self.notification.status, Notification.Status.ACCEPTED)
        self.assertIsNotNone(self.notification.sent_at)
        self.assertIsNone(self.notification.acknowledged_at)
        self.assertIsNone(self.notification.latency_seconds)
        self.assertFalse(latency_report(Notification.Kind.PACKAGING_VIDEO)["ok"])

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        receipt = NotificationDeliveryEvent.objects.get()
        self.assertEqual(self.notification.status, Notification.Status.SENT)
        self.assertIsNotNone(self.notification.acknowledged_at)
        self.assertEqual(receipt.outcome, NotificationDeliveryEvent.Outcome.DELIVERED)
        self.assertNotIn("must-not-be-stored", str(receipt.redacted_payload))
        self.assertNotIn("+923001112222", str(receipt.redacted_payload))
        self.assertTrue(latency_report(Notification.Kind.PACKAGING_VIDEO)["ok"])

    def test_unacknowledged_acceptance_is_counted_once(self):
        report = latency_report(Notification.Kind.PACKAGING_VIDEO)

        self.assertEqual(report["pending"], 1)

    def test_late_failure_cannot_reverse_a_delivered_acknowledgement(self):
        delivered = self._post(self._payload(event_id="receipt-delivered"))
        failed = self._post(
            self._payload(event_id="receipt-late-failure", status="failed")
        )

        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(failed.status_code, 200)
        self.notification.refresh_from_db()
        late_event = NotificationDeliveryEvent.objects.get(
            provider_event_id="receipt-late-failure"
        )
        self.assertEqual(self.notification.status, Notification.Status.SENT)
        self.assertIsNotNone(self.notification.acknowledged_at)
        self.assertEqual(late_event.outcome, NotificationDeliveryEvent.Outcome.IGNORED)

    def test_bad_signature_and_replay_are_safe(self):
        bad = self._post(self._payload(), secret="wrong")
        first = self._post(self._payload())
        replay = self._post(self._payload())

        self.assertEqual(bad.status_code, 403)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(NotificationDeliveryEvent.objects.count(), 1)

    def test_provider_failure_is_terminal_and_audited(self):
        response = self._post(self._payload(status="failed"))

        self.assertEqual(response.status_code, 200)
        self.notification.refresh_from_db()
        receipt = NotificationDeliveryEvent.objects.get()
        self.assertEqual(self.notification.status, Notification.Status.FAILED)
        self.assertEqual(receipt.outcome, NotificationDeliveryEvent.Outcome.FAILED)
        self.assertEqual(
            self.notification.terminal_error_class,
            "ProviderDeliveryFailure",
        )

    def test_oversized_provider_message_id_is_rejected_without_database_error(self):
        response = self._post(
            {
                **self._payload(event_id="receipt-oversized-id"),
                "provider_message_id": "m" * 256,
            }
        )

        self.assertEqual(response.status_code, 422)
        event = NotificationDeliveryEvent.objects.get(
            provider_event_id="receipt-oversized-id"
        )
        self.assertEqual(event.outcome, NotificationDeliveryEvent.Outcome.REJECTED)
        self.assertEqual(event.error_code, "invalid_provider_message_id")


@override_settings(
    PRODUCTION_MODE=False,
    DEMO_MODE_ENABLED=True,
    REVIEW_LINK_BACKEND="simulated",
    BURK_REVIEW_BASE_URL="https://shop.example.invalid/review",
)
class ReviewLinkProviderTests(TestCase):
    def test_configured_provider_builds_event_specific_opaque_links(self):
        order = make_order(ref="SO-PUBLIC-LEAK")
        provider = get_review_link_provider()

        first = provider.build(order, event_key="delivered:event-1")
        second = provider.build(order, event_key="delivered:event-2")

        self.assertTrue(first.startswith("https://shop.example.invalid/review?token="))
        self.assertNotIn(order.reference, first)
        self.assertNotIn(order.external_id, first)
        self.assertNotEqual(first, second)
