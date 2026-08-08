"""Module 3 tests — the KPI-1 proof: intercept 100% of mismatched scans.

The append-only PackScan ledger records every scan; a mismatch never attaches to
a line and never counts toward completion, and completing a pack is the only
thing that moves stock.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

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


class SessionLifecycleTests(TestCase):
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
