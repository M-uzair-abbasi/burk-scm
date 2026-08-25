"""Module 5 tests: instant automatic booking + courier status progression, and
Module 6's delivery trigger (the review reminder gets scheduled, not sent)."""

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlsplit
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from orders.models import SalesOrder
from notifications.models import Notification
from operations.models import WorkItem
from operations.services import process_due
from logistics.couriers.base import BookingResult
from logistics.models import CourierWebhookEvent, Shipment, ShipmentEvent
from logistics.services import (
    BOOK_SHIPMENT_KIND,
    advance_shipment,
    book_shipment,
    enqueue_shipment_booking,
    shipment_integrity,
    shipment_job_detail,
)

User = get_user_model()


def make_order(ref="SO-L0001", status="packed"):
    return SalesOrder.objects.create(
        channel="burk",
        external_id=ref,
        reference=ref,
        status=status,
        customer_name="Ship Buyer",
        customer_email="ship.buyer@example.invalid",
        customer_phone="+923004440001",
        shipping_address="123 Demo Street, Lahore",
        item_count=1,
        total="100.00",
    )


class BookShipmentTests(TestCase):
    def test_books_a_shipment_and_ships_the_order(self):
        order = make_order()
        shipment = book_shipment(order)

        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.SHIPPED)
        self.assertEqual(shipment.status, Shipment.Status.BOOKED)
        self.assertTrue(shipment.tracking_number)
        self.assertEqual(ShipmentEvent.objects.filter(shipment=shipment).count(), 1)

    def test_dispatches_tracking_notification_on_both_channels(self):
        order = make_order()
        book_shipment(order)
        notes = Notification.objects.filter(
            order=order, kind=Notification.Kind.SHIPMENT_TRACKING
        )
        self.assertEqual(notes.count(), 2)
        self.assertTrue(
            all(n.status == Notification.Status.SCHEDULED for n in notes)
        )
        process_due(limit=10)
        for n in notes:
            n.refresh_from_db()
            self.assertEqual(n.status, Notification.Status.SENT)
            self.assertLess(n.latency_seconds, 5)

    def test_booking_twice_is_idempotent(self):
        order = make_order()
        first = book_shipment(order)
        second = book_shipment(order)
        self.assertEqual(first.id, second.id)
        self.assertEqual(Shipment.objects.filter(order=order).count(), 1)

    def test_cannot_book_an_order_that_is_not_packed(self):
        order = make_order(status="pending")
        with self.assertRaises(ValidationError):
            book_shipment(order)

    def test_direct_booking_surfaces_carrier_outage_for_worker_retry(self):
        from unittest.mock import patch

        order = make_order()
        with (
            patch(
                "logistics.services.get_carrier",
                side_effect=RuntimeError("courier API down"),
            ),
            self.assertRaises(RuntimeError),
        ):
            book_shipment(order)
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.PACKED)
        self.assertFalse(Shipment.objects.filter(order=order).exists())


class QueuedShipmentBookingTests(TestCase):
    def test_enqueue_is_idempotent_and_does_not_touch_carrier(self):
        from unittest.mock import patch

        order = make_order(ref="SO-L-QUEUED")
        with patch("logistics.services.get_carrier") as carrier:
            first = enqueue_shipment_booking(order)
            second = enqueue_shipment_booking(order)

        carrier.assert_not_called()
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            WorkItem.objects.filter(kind=BOOK_SHIPMENT_KIND).count(), 1
        )
        self.assertEqual(shipment_job_detail(order)["status"], "pending")

    def test_worker_books_once_and_enqueues_tracking_notifications(self):
        order = make_order(ref="SO-L-WORKER")
        enqueue_shipment_booking(order)

        process_due(limit=1, worker_name="shipment-test")

        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.SHIPPED)
        self.assertEqual(Shipment.objects.filter(order=order).count(), 1)
        self.assertEqual(ShipmentEvent.objects.count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                order=order, kind=Notification.Kind.SHIPMENT_TRACKING
            ).count(),
            2,
        )
        self.assertEqual(shipment_job_detail(order)["status"], "succeeded")

    def test_carrier_outage_retries_then_succeeds_without_duplicate_booking(self):
        from unittest.mock import Mock, patch

        order = make_order(ref="SO-L-RETRY")
        item = enqueue_shipment_booking(order)
        carrier = Mock()
        carrier.book.side_effect = [
            RuntimeError("courier unavailable"),
            BookingResult(
                courier="tcs",
                tracking_number="TCS-RETRY-1",
                raw={"provider": "test"},
            ),
        ]

        with patch("logistics.services.get_carrier", return_value=carrier):
            process_due(limit=1)
            item.refresh_from_db()
            self.assertEqual(item.status, WorkItem.Status.RETRY)
            self.assertEqual(shipment_job_detail(order)["status"], "retry")

            WorkItem.objects.filter(pk=item.pk).update(available_at=timezone.now())
            process_due(limit=1)

        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.Status.SUCCEEDED)
        self.assertEqual(Shipment.objects.filter(order=order).count(), 1)
        self.assertEqual(ShipmentEvent.objects.count(), 1)
        self.assertEqual(carrier.book.call_count, 2)

    @override_settings(SHIPMENT_BOOKING_MAX_ATTEMPTS=1)
    def test_terminal_carrier_failure_remains_visible(self):
        from unittest.mock import patch

        order = make_order(ref="SO-L-FAILED")
        enqueue_shipment_booking(order)
        with patch(
            "logistics.services.get_carrier",
            side_effect=RuntimeError("credentials rejected"),
        ):
            process_due(limit=1)

        detail = shipment_job_detail(order)
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["attempts"], 1)
        self.assertIn("credentials rejected", detail["error"])
        self.assertFalse(Shipment.objects.filter(order=order).exists())


class CarrierRequestSnapshotTests(TestCase):
    def test_enqueue_freezes_structured_request_before_worker_or_resync_changes(self):
        from unittest.mock import Mock, patch

        order = SalesOrder.objects.create(
            channel="burk",
            external_id="CARRIER-SNAPSHOT",
            reference="SO-CARRIER-SNAPSHOT",
            status=SalesOrder.Status.PACKED,
            customer_name="Snapshot Buyer",
            customer_phone="+923001112233",
            shipping_address="12 Original Road, Lahore",
            shipping_address_line1="12 Original Road",
            shipping_address_line2="Suite 4",
            shipping_city="Lahore",
            shipping_province="Punjab",
            shipping_postal_code="54000",
            shipping_country="PK",
            item_count=2,
            currency="PKR",
            total="2500.00",
            cod_amount="2500.00",
            payment_mode="cod",
            parcel_weight_kg="1.250",
            parcel_length_cm="30.00",
            parcel_width_cm="20.00",
            parcel_height_cm="10.00",
            shipping_service_type="overnight",
            pickup_account="LHR-WH-1",
            customer_instructions="Call on arrival",
        )
        item = enqueue_shipment_booking(order)
        SalesOrder.objects.filter(pk=order.pk).update(
            shipping_address_line1="Changed after enqueue",
            customer_phone="+923009999999",
            total="9999.00",
        )
        carrier = Mock()
        carrier.book.return_value = BookingResult(
            courier="tcs",
            tracking_number="TCS-SNAPSHOT-1",
            provider_booking_id="provider-booking-1",
            label_reference="provider-label-1",
            raw={
                "booking_id": "provider-booking-1",
                "access_token": "must-not-be-stored",
                "customer": {"phone": "+923001112233"},
            },
        )

        with patch("logistics.services.get_carrier", return_value=carrier):
            process_due(limit=1)

        request = carrier.book.call_args.args[0]
        shipment = Shipment.objects.get(order=order)
        self.assertEqual(request.address_line1, "12 Original Road")
        self.assertEqual(request.phone, "+923001112233")
        self.assertEqual(str(request.declared_value), "2500.00")
        self.assertEqual(request.idempotency_key, f"burk-shipment-order-{order.pk}")
        self.assertEqual(
            item.payload["booking_request"]["address_line1"], "12 Original Road"
        )
        self.assertEqual(shipment.booking_request["address_line1"], "12 Original Road")
        self.assertEqual(shipment.request_idempotency_key, request.idempotency_key)
        self.assertEqual(shipment.provider_booking_id, "provider-booking-1")
        self.assertEqual(shipment.label_reference, "provider-label-1")
        self.assertNotIn("must-not-be-stored", str(shipment.raw_response))
        self.assertNotIn("+923001112233", str(shipment.raw_response))

    def test_invalid_carrier_request_fails_before_adapter_io(self):
        from unittest.mock import patch

        order = SalesOrder.objects.create(
            channel="burk",
            external_id="CARRIER-INVALID",
            reference="SO-CARRIER-INVALID",
            status=SalesOrder.Status.PACKED,
            customer_name="",
            customer_phone="",
            shipping_address="",
            item_count=1,
            total="100.00",
        )

        with patch("logistics.services.get_carrier") as get_carrier:
            with self.assertRaises(ValidationError):
                enqueue_shipment_booking(order)

        get_carrier.assert_not_called()


@override_settings(REVIEW_REMINDER_DELAY_SECONDS=60)
class AdvanceShipmentTests(TestCase):
    def setUp(self):
        self.order = make_order()
        self.shipment = book_shipment(self.order)

    def test_advance_to_in_transit(self):
        event = advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        self.shipment.refresh_from_db()
        self.assertEqual(event.status, Shipment.Status.IN_TRANSIT)
        self.assertEqual(self.shipment.status, Shipment.Status.IN_TRANSIT)
        self.assertIsNotNone(self.shipment.in_transit_at)

    def test_delivered_flips_order_and_schedules_review_reminder(self):
        advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        with self.captureOnCommitCallbacks(execute=True):
            advance_shipment(self.shipment, Shipment.Status.DELIVERED)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, SalesOrder.Status.DELIVERED)

        review = Notification.objects.filter(
            order=self.order, kind=Notification.Kind.REVIEW_REQUEST
        )
        self.assertEqual(review.count(), 2)
        for n in review:
            self.assertEqual(n.status, Notification.Status.SCHEDULED)
            self.assertIsNotNone(n.scheduled_for)
            review_url = urlsplit(n.payload["review_link"])
            query = parse_qs(review_url.query)
            self.assertNotIn(self.order.reference, review_url.path)
            self.assertNotIn(f"/{self.order.pk}", review_url.path)
            self.assertNotIn("order_id", query)
            self.assertEqual(len(query.get("token", [])), 1)

    def test_cannot_go_backward(self):
        advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        with self.assertRaises(ValidationError):
            advance_shipment(self.shipment, Shipment.Status.BOOKED)

    def test_cannot_advance_past_delivered(self):
        advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        advance_shipment(self.shipment, Shipment.Status.DELIVERED)
        with self.assertRaises(ValidationError):
            advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)


class CourierWebhookTests(TestCase):
    def setUp(self):
        self.order = make_order(ref="SO-L-WEBHOOK")
        self.shipment = book_shipment(self.order)
        self.secret = "test-courier-webhook-secret"
        self.settings = override_settings(
            COURIER_WEBHOOK_SECRETS={self.shipment.courier: self.secret}
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.url = f"/api/courier-webhooks/{self.shipment.courier}/"

    def _post(self, payload, *, secret=None):
        body = json.dumps(payload, separators=(",", ":")).encode()
        digest = hmac.new(
            (secret if secret is not None else self.secret).encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_COURIER_SIGNATURE=f"sha256={digest}",
        )

    def _payload(self, *, event_id="evt-1", status="in_transit"):
        return {
            "event_id": event_id,
            "tracking_number": self.shipment.tracking_number,
            "status": status,
            "phone": "+923001234567",
            "access_token": "must-not-be-stored",
        }

    def test_missing_or_bad_signature_is_rejected_without_audit_row(self):
        body = json.dumps(self._payload()).encode()
        missing = self.client.post(
            self.url, data=body, content_type="application/json"
        )
        bad = self._post(self._payload(), secret="wrong-secret")

        self.assertEqual(missing.status_code, 403)
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(CourierWebhookEvent.objects.count(), 0)

    def test_valid_event_advances_once_and_stores_only_redacted_payload(self):
        response = self._post(self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["replayed"])
        self.shipment.refresh_from_db()
        event = CourierWebhookEvent.objects.get()
        self.assertEqual(self.shipment.status, Shipment.Status.IN_TRANSIT)
        self.assertEqual(event.outcome, CourierWebhookEvent.Outcome.PROCESSED)
        self.assertEqual(event.mapped_status, Shipment.Status.IN_TRANSIT)
        self.assertNotIn("must-not-be-stored", str(event.redacted_payload))
        self.assertNotIn("+923001234567", str(event.redacted_payload))
        self.assertEqual(
            ShipmentEvent.objects.filter(
                shipment=self.shipment, status=Shipment.Status.IN_TRANSIT
            ).count(),
            1,
        )

    def test_replay_is_idempotent_and_different_duplicate_status_is_ignored(self):
        first = self._post(self._payload(event_id="evt-1"))
        replay = self._post(self._payload(event_id="evt-1"))
        duplicate_status = self._post(self._payload(event_id="evt-2"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(duplicate_status.status_code, 200)
        self.assertEqual(
            CourierWebhookEvent.objects.get(provider_event_id="evt-2").outcome,
            CourierWebhookEvent.Outcome.IGNORED,
        )
        self.assertEqual(CourierWebhookEvent.objects.count(), 2)
        self.assertEqual(
            ShipmentEvent.objects.filter(
                shipment=self.shipment, status=Shipment.Status.IN_TRANSIT
            ).count(),
            1,
        )

    def test_unknown_status_is_audited_and_returns_unprocessable(self):
        response = self._post(self._payload(status="teleported"))

        self.assertEqual(response.status_code, 422)
        event = CourierWebhookEvent.objects.get()
        self.assertEqual(event.outcome, CourierWebhookEvent.Outcome.REJECTED)
        self.assertEqual(event.error_code, "unknown_status")


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locks")
class ConcurrentCourierWebhookTests(TransactionTestCase):
    reset_sequences = True

    def test_two_distinct_events_for_one_transition_create_one_status_event(self):
        order = make_order(ref="SO-L-WEBHOOK-RACE")
        shipment = book_shipment(order)
        secret = "concurrent-webhook-secret"
        settings_override = override_settings(
            COURIER_WEBHOOK_SECRETS={shipment.courier: secret}
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        barrier = Barrier(2)

        def post_event(event_id):
            payload = {
                "event_id": event_id,
                "tracking_number": shipment.tracking_number,
                "status": "in_transit",
            }
            body = json.dumps(payload, separators=(",", ":")).encode()
            digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            try:
                barrier.wait(timeout=10)
                return Client().post(
                    f"/api/courier-webhooks/{shipment.courier}/",
                    data=body,
                    content_type="application/json",
                    HTTP_X_COURIER_SIGNATURE=f"sha256={digest}",
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(post_event, ["evt-race-1", "evt-race-2"]))

        shipment.refresh_from_db()
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(shipment.status, Shipment.Status.IN_TRANSIT)
        self.assertEqual(
            ShipmentEvent.objects.filter(
                shipment=shipment, status=Shipment.Status.IN_TRANSIT
            ).count(),
            1,
        )
        self.assertEqual(
            set(CourierWebhookEvent.objects.values_list("outcome", flat=True)),
            {
                CourierWebhookEvent.Outcome.PROCESSED,
                CourierWebhookEvent.Outcome.IGNORED,
            },
        )


class ShipmentIntegrityTests(TestCase):
    def test_ok_when_every_shipped_order_has_a_shipment(self):
        book_shipment(make_order())
        report = shipment_integrity()
        self.assertTrue(report["ok"])

    def test_ignores_an_order_the_channel_reports_as_already_shipped(self):
        # Arrives pre-shipped from the channel feed itself — this system never
        # packed it, so it's out of scope, not a breach.
        make_order(status="shipped")
        report = shipment_integrity()
        self.assertTrue(report["ok"])
        self.assertEqual(report["missing_shipment_orders"], [])

    def test_flags_an_order_we_packed_ourselves_with_no_shipment(self):
        # Simulates the real gap this check exists to catch: fulfillment
        # completed a pack (so booking *should* have followed) but never
        # went through book_shipment — calling fulfillment.services directly,
        # bypassing PackingViewSet.complete()'s automatic chaining.
        from inventory.models import Product, StockMovement
        from inventory.services import record_movement
        from orders.models import SalesOrderLine
        from fulfillment.services import complete_packing, record_scan, start_packing

        product = Product.objects.create(sku="BRK-L001", name="BRK-L001", barcode="7770001")
        record_movement(product=product, quantity_delta=5, reason=StockMovement.Reason.INITIAL)
        order = make_order(status="pending")
        SalesOrderLine.objects.create(
            order=order, sku=product.sku, product=product, product_name=product.sku,
            quantity=1, unit_price="100.00", line_total="100.00",
        )
        session = start_packing(order)
        record_scan(session, "7770001")
        complete_packing(session)  # no book_shipment() call — the gap

        report = shipment_integrity()
        self.assertFalse(report["ok"])
        self.assertIn(order.reference, report["missing_shipment_orders"])


@override_settings(DEMO_ACTIONS_ENABLED=True)
class ShipmentAdvanceAuthorizationTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="shipment-operator",
            password="x",
            role=User.Role.OPERATOR,
        )
        self.manager = User.objects.create_user(
            username="shipment-manager",
            password="x",
            role=User.Role.MANAGER,
        )
        self.shipment = book_shipment(make_order(ref="SO-L-AUTH"))
        self.client = APIClient()
        self.url = f"/api/shipments/{self.shipment.id}/advance/"

    def test_anonymous_cannot_simulate_shipment_advance(self):
        response = self.client.post(
            self.url, {"status": Shipment.Status.IN_TRANSIT}, format="json"
        )

        self.assertIn(response.status_code, {401, 403})

    def test_operator_cannot_simulate_shipment_advance(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            self.url, {"status": Shipment.Status.IN_TRANSIT}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_manager_can_simulate_shipment_advance(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            self.url, {"status": Shipment.Status.IN_TRANSIT}, format="json"
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(DEMO_ACTIONS_ENABLED=False)
    def test_simulation_endpoint_is_absent_when_demo_actions_disabled(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            self.url, {"status": Shipment.Status.IN_TRANSIT}, format="json"
        )

        self.assertEqual(response.status_code, 404)
