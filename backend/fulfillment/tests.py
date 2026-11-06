"""Module 3 tests — the KPI-1 proof: intercept 100% of mismatched scans.

The append-only PackScan ledger records every scan; a mismatch never attaches to
a line and never counts toward completion, and completing a pack is the only
thing that moves stock.
"""

import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from inventory.models import Product, StockMovement
from inventory.services import ledger_balance, record_movement
from orders.models import SalesOrder, SalesOrderLine
from fulfillment.models import PackingSession, PackScan
from fulfillment.services import (
    complete_packing,
    confirm_line_manual,
    packing_queue,
    record_scan,
    session_progress,
    start_packing,
)
from surveillance.models import PackagingRecording

User = get_user_model()


WEBM_MAGIC = b"\x1a\x45\xdf\xa3"


def make_video(content: bytes = b"fake-browser-video-bytes") -> SimpleUploadedFile:
    """A fake upload that still carries a real WebM header, since the upload
    endpoint now rejects anything that doesn't -- see detect_container()."""
    return SimpleUploadedFile(
        "clip.webm", WEBM_MAGIC + content, content_type="video/webm"
    )


def make_product(sku, barcode, stock=100):
    p = Product.objects.create(sku=sku, name=sku, barcode=barcode)
    if stock:
        record_movement(
            product=p, quantity_delta=stock, reason=StockMovement.Reason.INITIAL
        )
    return p


def make_order(ref="SO-T0001", status="pending", lines=None, channel="burk"):
    order = SalesOrder.objects.create(
        channel=channel, external_id=ref, reference=ref, status=status
    )
    for prod, qty in lines or []:
        SalesOrderLine.objects.create(
            order=order,
            sku=prod.sku if prod else "X",
            product=prod,
            product_name=prod.sku if prod else "X",
            quantity=qty,
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00") * qty,
        )
    return order


class ScanValidationTests(TestCase):
    def setUp(self):
        self.p1 = make_product("BRK-A", "1111")
        self.p2 = make_product("BRK-B", "2222")
        self.other = make_product("BRK-Z", "9999")  # exists but not on the order
        self.order = make_order(lines=[(self.p1, 2), (self.p2, 1)])
        self.session = start_packing(self.order)

    def test_matched_scan_is_ok(self):
        scan = record_scan(self.session, "1111")
        self.assertEqual(scan.result, "ok")
        self.assertEqual(scan.line.product_id, self.p1.id)

    def test_unknown_barcode_is_mismatch(self):
        scan = record_scan(self.session, "0000")
        self.assertEqual(scan.result, "mismatch")
        self.assertIsNone(scan.line)

    def test_product_not_on_order_is_mismatch(self):
        scan = record_scan(self.session, "9999")
        self.assertEqual(scan.result, "mismatch")
        self.assertIsNone(scan.line)
        self.assertEqual(scan.product_id, self.other.id)  # recognised, but wrong order

    def test_overscan_beyond_quantity(self):
        first = record_scan(self.session, "2222")  # p2 qty 1 -> done
        second = record_scan(self.session, "2222")  # again -> overscan
        self.assertEqual(first.result, "ok")
        self.assertEqual(second.result, "overscan")

    def test_progress_counts_only_ok_scans(self):
        record_scan(self.session, "1111")
        record_scan(self.session, "0000")  # mismatch — must not count
        prog = session_progress(self.session)
        p1line = next(l for l in prog["lines"] if l["line"].product_id == self.p1.id)
        self.assertEqual(p1line["scanned"], 1)
        self.assertFalse(prog["complete"])

    def test_hundred_percent_interception(self):
        # A mixed stream: valid scans progress; EVERY invalid one is flagged.
        stream = ["1111", "0000", "1111", "9999", "2222", "0000"]
        results = [record_scan(self.session, b).result for b in stream]
        self.assertEqual(
            results, ["ok", "mismatch", "ok", "mismatch", "ok", "mismatch"]
        )
        mismatches = PackScan.objects.filter(session=self.session, result="mismatch")
        self.assertEqual(mismatches.count(), 3)
        # No mismatch ever attaches to a line -> none counted as packed.
        self.assertFalse(mismatches.filter(line__isnull=False).exists())
        # The valid scans still completed the order.
        self.assertTrue(session_progress(self.session)["complete"])

    def test_packscan_is_append_only(self):
        scan = record_scan(self.session, "1111")
        scan.result = "mismatch"
        with self.assertRaises(ValueError):
            scan.save()


class CompleteTests(TestCase):
    def test_complete_refused_when_incomplete(self):
        p = make_product("BRK-A", "1111", stock=10)
        order = make_order(lines=[(p, 3)])
        session = start_packing(order)
        record_scan(session, "1111")  # 1/3
        with self.assertRaises(ValidationError):
            complete_packing(session)

    def test_complete_decrements_stock_and_packs(self):
        p = make_product("BRK-A", "1111", stock=10)
        order = make_order(lines=[(p, 3)])
        session = start_packing(order)
        for _ in range(3):
            record_scan(session, "1111")
        packed = complete_packing(session)
        self.assertEqual(packed.status, "packed")
        p.refresh_from_db()
        self.assertEqual(p.quantity_on_hand, 7)  # 10 - 3
        self.assertEqual(ledger_balance(p), 7)
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")
        self.assertIsNotNone(session.completed_at)

    def test_oversell_guard_blocks_completion(self):
        p = make_product("BRK-LOW", "5555", stock=2)
        order = make_order(ref="SO-T0002", lines=[(p, 3)])
        session = start_packing(order)
        for _ in range(3):
            record_scan(session, "5555")  # scanning doesn't check stock
        with self.assertRaises(ValidationError):
            complete_packing(session)
        # Nothing half-applied: transaction rolled back.
        p.refresh_from_db()
        self.assertEqual(p.quantity_on_hand, 2)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locking")
class ConcurrentPackingCompletionTests(TransactionTestCase):
    reset_sequences = True

    def test_duplicate_completion_has_one_stock_effect(self):
        product = make_product("BRK-PACK-RACE", "RACE-PACK", stock=10)
        order = make_order(ref="SO-PACK-RACE", lines=[(product, 1)])
        session = start_packing(order)
        record_scan(session, product.barcode)
        barrier = Barrier(2)

        def complete_once(_):
            try:
                local_session = PackingSession.objects.get(pk=session.pk)
                barrier.wait(timeout=10)
                return complete_packing(local_session).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            order_ids = list(pool.map(complete_once, range(2)))

        product.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(order_ids, [order.id, order.id])
        self.assertEqual(product.quantity_on_hand, 9)
        self.assertEqual(
            StockMovement.objects.filter(
                product=product,
                reason=StockMovement.Reason.SALE,
                note__contains=order.reference,
            ).count(),
            1,
        )
        self.assertEqual(session.status, PackingSession.Status.COMPLETED)


class ManualConfirmTests(TestCase):
    def test_manual_confirm_barcodeless_line(self):
        barcoded = make_product("BRK-A", "1111", stock=10)
        barcodeless = Product.objects.create(sku="BRK-NB", name="No Barcode")
        record_movement(
            product=barcodeless, quantity_delta=10, reason=StockMovement.Reason.INITIAL
        )
        order = make_order(lines=[(barcoded, 1), (barcodeless, 1)])
        session = start_packing(order)

        record_scan(session, "1111")  # barcoded line done
        self.assertFalse(session_progress(session)["complete"])
        nb_line = order.lines.get(product=barcodeless)
        scan = confirm_line_manual(session, nb_line)
        self.assertTrue(scan.manual)
        self.assertEqual(scan.result, "ok")
        self.assertTrue(session_progress(session)["complete"])
        packed = complete_packing(session)
        self.assertEqual(packed.status, "packed")

    def test_manual_confirm_rejects_barcoded_line(self):
        product = make_product("BRK-BAR", "3333", stock=10)
        order = make_order(ref="SO-BARCODE", lines=[(product, 1)])
        session = start_packing(order)

        with self.assertRaisesMessage(ValidationError, "must be scanned"):
            confirm_line_manual(session, order.lines.get())


class SessionLifecycleTests(TestCase):
    def test_empty_order_cannot_start_packing(self):
        order = make_order(ref="SO-EMPTY", lines=[])

        with self.assertRaisesMessage(ValidationError, "at least one line"):
            start_packing(order)

    def test_empty_order_is_never_complete(self):
        order = make_order(ref="SO-EMPTY-PROGRESS", lines=[])
        session = PackingSession.objects.create(order=order)

        self.assertFalse(session_progress(session)["complete"])

    def test_refuse_packing_non_packable_order(self):
        p = make_product("BRK-A", "1111")
        order = make_order(status="shipped", lines=[(p, 1)])
        with self.assertRaises(ValidationError):
            start_packing(order)

    def test_start_packing_is_idempotent(self):
        p = make_product("BRK-A", "1111")
        order = make_order(lines=[(p, 1)])
        self.assertEqual(start_packing(order).id, start_packing(order).id)

    def test_queue_lists_packable_oldest_first(self):
        p = make_product("BRK-A", "1111")
        make_order(ref="SO-OLD", status="pending", lines=[(p, 1)])
        make_order(ref="SO-CONF", status="confirmed", lines=[(p, 1)])
        make_order(ref="SO-SHIP", status="shipped", lines=[(p, 1)])
        refs = [o.reference for o in packing_queue()]
        self.assertIn("SO-OLD", refs)
        self.assertIn("SO-CONF", refs)
        self.assertNotIn("SO-SHIP", refs)  # shipped is not awaiting packing


class PackIntegrityCommandTests(TestCase):
    def test_check_fails_without_completed_pack_evidence(self):
        with self.assertRaises(SystemExit) as raised:
            call_command("check_pack_integrity", "--check")

        self.assertEqual(raised.exception.code, 1)

    def test_check_fails_for_completed_empty_session(self):
        order = make_order(ref="SO-EMPTY-COMPLETE", lines=[])
        PackingSession.objects.create(
            order=order,
            status=PackingSession.Status.COMPLETED,
        )

        with self.assertRaises(SystemExit) as raised:
            call_command("check_pack_integrity", "--check")

        self.assertEqual(raised.exception.code, 1)


class PackingAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="pack-owner", password="x", role=User.Role.OPERATOR
        )
        self.other_operator = User.objects.create_user(
            username="pack-other", password="x", role=User.Role.OPERATOR
        )
        self.manager = User.objects.create_user(
            username="pack-manager", password="x", role=User.Role.MANAGER
        )
        self.product = make_product("BRK-AUTH", "AUTH-111", stock=10)
        self.order = make_order(ref="SO-AUTH", lines=[(self.product, 1)])
        self.session = start_packing(self.order, user=self.owner)
        self.client = APIClient()

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_owner_and_manager_can_retrieve_session(self):
        for user in (self.owner, self.manager):
            with self.subTest(user=user.username):
                self._authenticate(user)
                response = self.client.get(f"/api/packing/{self.session.id}/")
                self.assertEqual(response.status_code, 200)

    def test_non_owner_cannot_retrieve_session(self):
        self._authenticate(self.other_operator)

        response = self.client.get(f"/api/packing/{self.session.id}/")

        self.assertEqual(response.status_code, 404)

    def test_non_owner_cannot_scan_session(self):
        self._authenticate(self.other_operator)

        response = self.client.post(
            f"/api/packing/{self.session.id}/scan/",
            {"barcode": self.product.barcode},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.session.scans.exists())

    def test_non_owner_cannot_confirm_line(self):
        barcodeless = Product.objects.create(sku="BRK-AUTH-NB", name="No Barcode")
        record_movement(
            product=barcodeless,
            quantity_delta=1,
            reason=StockMovement.Reason.INITIAL,
        )
        line = SalesOrderLine.objects.create(
            order=self.order,
            sku=barcodeless.sku,
            product=barcodeless,
            product_name=barcodeless.name,
            quantity=1,
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        self._authenticate(self.other_operator)

        response = self.client.post(
            f"/api/packing/{self.session.id}/confirm-line/",
            {"line": line.id},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.session.scans.exists())

    def test_non_owner_cannot_complete_session(self):
        record_scan(self.session, self.product.barcode, user=self.owner)
        self._authenticate(self.other_operator)

        with (
            patch("fulfillment.views.seal_recording"),
            patch("fulfillment.views.enqueue_shipment_booking"),
        ):
            response = self.client.post(
                f"/api/packing/{self.session.id}/complete/", {}, format="json"
            )

        self.assertEqual(response.status_code, 404)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, PackingSession.Status.IN_PROGRESS)

    def test_non_owner_cannot_cancel_session(self):
        self._authenticate(self.other_operator)

        response = self.client.post(
            f"/api/packing/{self.session.id}/cancel/", {}, format="json"
        )

        self.assertEqual(response.status_code, 404)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, PackingSession.Status.IN_PROGRESS)

    def test_non_owner_cannot_upload_recording(self):
        self._authenticate(self.other_operator)

        response = self.client.post(
            f"/api/packing/{self.session.id}/recording/",
            {"video": make_video()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)

    def test_non_owner_cannot_claim_existing_active_session(self):
        self._authenticate(self.other_operator)

        response = self.client.post(
            "/api/packing/", {"order": self.order.id}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.operator, self.owner)


@override_settings(PACKAGING_CAMERA_BACKEND="browser")
class RecordingUploadTests(TestCase):
    """The browser-camera upload endpoint: Module 4's client-side capture."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

        self.user = User.objects.create_user(
            username="upload-op", password="x", role=User.Role.OPERATOR
        )
        self.product = make_product("BRK-UPLOAD", "UPLOAD-111", stock=5)
        self.order = make_order(ref="SO-UPLOAD", lines=[(self.product, 1)])
        # Carrier booking (triggered by /complete/) needs a real shipping
        # address -- make_order() deliberately leaves this blank for the
        # other tests in this file that never reach that far.
        self.order.customer_name = "Upload Buyer"
        self.order.customer_phone = "+923001230055"
        self.order.shipping_address_line1 = "1 Test Street"
        self.order.shipping_city = "Lahore"
        self.order.shipping_province = "Punjab"
        self.order.shipping_country = "PK"
        self.order.item_count = 1
        self.order.save()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        start_response = self.client.post(
            "/api/packing/", {"order": self.order.id}, format="json"
        )
        self.session_id = start_response.data["id"]
        self.recording = PackagingRecording.objects.get(session_id=self.session_id)

    def test_upload_lands_the_bytes_at_the_reserved_raw_path(self):
        response = self.client.post(
            f"/api/packing/{self.session_id}/recording/",
            {"video": make_video(b"real-looking-webm-bytes")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        raw_abs = Path(self._tmp.name) / self.recording.raw_path
        self.assertEqual(
            raw_abs.read_bytes(), WEBM_MAGIC + b"real-looking-webm-bytes"
        )

    def test_missing_file_is_rejected(self):
        response = self.client.post(
            f"/api/packing/{self.session_id}/recording/", {}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)

    def test_non_video_upload_is_rejected(self):
        not_a_video = SimpleUploadedFile(
            "clip.webm", b"<html>not a video</html>", content_type="video/webm"
        )

        response = self.client.post(
            f"/api/packing/{self.session_id}/recording/",
            {"video": not_a_video},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        raw_abs = Path(self._tmp.name) / self.recording.raw_path
        self.assertFalse(raw_abs.exists())

    def test_oversized_upload_is_rejected(self):
        with override_settings(PACKAGING_UPLOAD_MAX_BYTES=10):
            response = self.client.post(
                f"/api/packing/{self.session_id}/recording/",
                {"video": make_video(b"this upload is longer than ten bytes")},
                format="multipart",
            )

        self.assertEqual(response.status_code, 400)
        raw_abs = Path(self._tmp.name) / self.recording.raw_path
        self.assertFalse(raw_abs.exists())

    def test_upload_after_sealing_is_rejected(self):
        record_scan(
            self.order.packing_sessions.get(pk=self.session_id),
            self.product.barcode,
            user=self.user,
        )
        complete_response = self.client.post(
            f"/api/packing/{self.session_id}/complete/", {}, format="json"
        )
        self.assertEqual(complete_response.status_code, 200)

        response = self.client.post(
            f"/api/packing/{self.session_id}/recording/",
            {"video": make_video()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)

    def test_re_upload_before_sealing_overwrites_the_previous_attempt(self):
        self.client.post(
            f"/api/packing/{self.session_id}/recording/",
            {"video": make_video(b"first attempt")},
            format="multipart",
        )
        response = self.client.post(
            f"/api/packing/{self.session_id}/recording/",
            {"video": make_video(b"second attempt")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        raw_abs = Path(self._tmp.name) / self.recording.raw_path
        self.assertEqual(raw_abs.read_bytes(), WEBM_MAGIC + b"second attempt")
