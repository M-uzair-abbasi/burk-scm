"""Module 5 tests: instant automatic booking + courier status progression, and
Module 6's delivery trigger (the review reminder gets scheduled, not sent)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings

from orders.models import SalesOrder
from notifications.models import Notification
from logistics.models import Shipment, ShipmentEvent
from logistics.services import advance_shipment, book_shipment, shipment_integrity


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
        # book_shipment() defers the dispatch to transaction.on_commit (so a
        # rolled-back booking never sends a real email/WhatsApp for a shipment
        # that no longer exists) — TestCase wraps tests in a transaction that's
        # always rolled back, so on_commit callbacks are captured explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            book_shipment(order)
        notes = Notification.objects.filter(
            order=order, kind=Notification.Kind.SHIPMENT_TRACKING
        )
        self.assertEqual(notes.count(), 2)
        for n in notes:
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

    def test_carrier_outage_degrades_to_no_shipment_without_raising(self):
        # A real courier integration's outage must not turn a successful pack
        # into a 500 — the caller (PackingViewSet.complete) never wraps this
        # call in anything broader than ValidationError.
        from unittest.mock import patch

        order = make_order()
        with patch("logistics.services.get_carrier", side_effect=RuntimeError("courier API down")):
            result = book_shipment(order)
        self.assertIsNone(result)
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.PACKED)
        self.assertFalse(Shipment.objects.filter(order=order).exists())


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

    def test_cannot_go_backward(self):
        advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        with self.assertRaises(ValidationError):
            advance_shipment(self.shipment, Shipment.Status.BOOKED)

    def test_cannot_advance_past_delivered(self):
        advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)
        advance_shipment(self.shipment, Shipment.Status.DELIVERED)
        with self.assertRaises(ValidationError):
            advance_shipment(self.shipment, Shipment.Status.IN_TRANSIT)


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
