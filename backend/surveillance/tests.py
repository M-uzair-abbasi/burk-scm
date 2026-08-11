"""Module 4 tests: capture -> compress -> dispatch, and its KPI #2 timing.

Runs the real ffmpeg binary (confirmed present in this environment) against a
temporary MEDIA_ROOT so test runs never touch backend/media/ or leave files
behind.
"""

import tempfile
from decimal import Decimal

from django.test import TestCase, override_settings

from inventory.models import Product, StockMovement
from inventory.services import record_movement
from orders.models import SalesOrder, SalesOrderLine
from fulfillment.services import complete_packing, record_scan, start_packing
from notifications.models import Notification
from surveillance.models import PackagingRecording
from surveillance.services import capture_and_dispatch


def make_product(sku, barcode, stock=10):
    p = Product.objects.create(sku=sku, name=sku, barcode=barcode)
    record_movement(product=p, quantity_delta=stock, reason=StockMovement.Reason.INITIAL)
    return p


def make_order(ref="SO-V0001", lines=None):
    order = SalesOrder.objects.create(
        channel="burk",
        external_id=ref,
        reference=ref,
        status="pending",
        customer_name="Video Buyer",
        customer_email="video.buyer@example.invalid",
        customer_phone="+923001230001",
    )
    for prod, qty in lines or []:
        SalesOrderLine.objects.create(
            order=order,
            sku=prod.sku,
            product=prod,
            product_name=prod.sku,
            quantity=qty,
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00") * qty,
        )
    return order


def sealed_session():
    product = make_product("BRK-V001", "5550001")
    order = make_order(lines=[(product, 1)])
    session = start_packing(order)
    record_scan(session, "5550001")
    complete_packing(session)
    session.refresh_from_db()
    return session


class CaptureAndDispatchTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

    def test_capture_and_dispatch_produces_a_ready_recording(self):
        session = sealed_session()
        recording = capture_and_dispatch(session)

        self.assertEqual(recording.status, PackagingRecording.Status.READY)
        self.assertTrue(recording.raw_path)
        self.assertTrue(recording.compressed_path)
        self.assertGreater(recording.raw_size_bytes, 0)
        self.assertGreater(recording.compressed_size_bytes, 0)
        # A genuine compression pass, not a copy — the point of running real ffmpeg.
        self.assertLess(recording.compressed_size_bytes, recording.raw_size_bytes)

    def test_calling_twice_is_idempotent(self):
        # A retried/duplicated "Complete pack" request must not raise on the
        # session<->recording OneToOne constraint or double-dispatch the video.
        session = sealed_session()
        first = capture_and_dispatch(session)
        second = capture_and_dispatch(session)
        self.assertEqual(first.id, second.id)
        self.assertEqual(PackagingRecording.objects.filter(session=session).count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                order=session.order, kind=Notification.Kind.PACKAGING_VIDEO
            ).count(),
            2,
        )

    def test_capture_and_dispatch_sends_within_kpi_2_budget(self):
        session = sealed_session()
        capture_and_dispatch(session)

        notes = Notification.objects.filter(
            order=session.order, kind=Notification.Kind.PACKAGING_VIDEO
        )
        self.assertEqual(notes.count(), 2)  # email + whatsapp
        for n in notes:
            self.assertEqual(n.status, Notification.Status.SENT)
            self.assertIsNotNone(n.latency_seconds)
            self.assertLess(n.latency_seconds, 180)  # KPI #2

    def test_notification_payload_carries_a_reachable_video_url(self):
        session = sealed_session()
        recording = capture_and_dispatch(session)
        note = Notification.objects.filter(
            order=session.order, kind=Notification.Kind.PACKAGING_VIDEO, channel="email"
        ).first()
        self.assertIn(recording.compressed_path, note.payload["video_url"])

    def test_ffmpeg_failure_marks_recording_failed_without_raising(self):
        session = sealed_session()
        with self._broken_camera():
            recording = capture_and_dispatch(session)
        self.assertEqual(recording.status, PackagingRecording.Status.FAILED)
        self.assertTrue(recording.error)
        self.assertFalse(
            Notification.objects.filter(
                order=session.order, kind=Notification.Kind.PACKAGING_VIDEO
            ).exists()
        )

    def _broken_camera(self):
        from unittest.mock import patch

        return patch(
            "surveillance.services.get_camera",
            side_effect=RuntimeError("camera offline"),
        )
