from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from inventory.models import Product, StockMovement
from inventory.services import ledger_balance, record_movement
from suppliers.models import Supplier, SupplierPriceTier, SupplierProduct

from .models import PurchaseOrder
from .serializers import PurchaseOrderLineSerializer
from .services import create_reorder_po, receive_po, submit_po

User = get_user_model()


class PurchasingServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="mgr", password="x", role=User.Role.MANAGER
        )
        # Low-stock product with a preferred supplier and two price tiers.
        self.product = Product.objects.create(
            sku="TEST-1", name="Test Kurta", safety_stock=25, reorder_quantity=60
        )
        record_movement(
            product=self.product,
            quantity_delta=8,
            reason=StockMovement.Reason.INITIAL,
            user=self.manager,
        )
        self.supplier = Supplier.objects.create(
            code="SUP-T", name="Test Supplier", default_lead_time_days=12
        )
        self.link = SupplierProduct.objects.create(
            supplier=self.supplier, product=self.product, is_preferred=True
        )
        SupplierPriceTier.objects.create(
            supplier_product=self.link, min_quantity=1, unit_price=Decimal("1950.00")
        )
        SupplierPriceTier.objects.create(
            supplier_product=self.link, min_quantity=60, unit_price=Decimal("1820.00")
        )
        # Product with no supplier link at all.
        self.no_supplier = Product.objects.create(
            sku="TEST-NO", name="Orphan", reorder_quantity=10
        )

    def test_reorder_creates_draft_with_preferred_supplier_and_tier_price(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        self.assertEqual(po.status, PurchaseOrder.Status.DRAFT)
        self.assertTrue(po.po_number.startswith("PO-"))
        self.assertEqual(po.supplier, self.supplier)
        line = po.lines.get()
        self.assertEqual(line.quantity_ordered, 60)
        # 60 units reaches the 60+ tier.
        self.assertEqual(line.unit_price, Decimal("1820.00"))
        self.assertEqual(po.total_amount, Decimal("109200.00"))

    def test_reorder_without_supplier_raises(self):
        with self.assertRaises(ValidationError):
            create_reorder_po(product=self.no_supplier, user=self.manager)

    def test_reorder_quantity_override_selects_matching_tier(self):
        po = create_reorder_po(product=self.product, user=self.manager, quantity=1)
        self.assertEqual(po.lines.get().unit_price, Decimal("1950.00"))

    def test_submit_sets_status_and_expected_date(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.SUBMITTED)
        self.assertIsNotNone(po.submitted_at)
        self.assertEqual(
            po.expected_date, timezone.localdate() + timedelta(days=12)
        )

    def test_submit_uses_preserved_supplier_product_lead_time(self):
        self.link.lead_time_days = 4
        self.link.save(update_fields=["lead_time_days"])
        po = create_reorder_po(product=self.product, user=self.manager)

        self.link.lead_time_days = 8
        self.link.save(update_fields=["lead_time_days"])
        self.supplier.default_lead_time_days = 20
        self.supplier.save(update_fields=["default_lead_time_days"])
        submit_po(po)

        po.refresh_from_db()
        self.assertEqual(
            po.expected_date,
            timezone.localdate() + timedelta(days=4),
        )

    def test_reorder_line_api_exposes_supplier_terms_snapshot(self):
        self.link.lead_time_days = 4
        self.link.save(update_fields=["lead_time_days"])
        po = create_reorder_po(product=self.product, user=self.manager)

        data = PurchaseOrderLineSerializer(po.lines.get()).data

        self.assertEqual(data.get("supplier_product"), self.link.id)
        self.assertEqual(data.get("effective_lead_time_days"), 4)
        self.assertEqual(data.get("price_tier_min_quantity"), 60)

    def test_submit_non_draft_raises(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        with self.assertRaises(ValidationError):
            submit_po(po)

    def test_receive_full_marks_received_and_raises_stock(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        receive_po(po, user=self.manager)
        po.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertIsNotNone(po.received_at)
        self.assertEqual(self.product.quantity_on_hand, 68)
        # Stock arrived via the ledger, and the cache still agrees with it.
        self.assertEqual(ledger_balance(self.product), 68)
        movement = StockMovement.objects.get(
            purchase_order=po, reason=StockMovement.Reason.PURCHASE_RECEIPT
        )
        self.assertEqual(movement.quantity_delta, 60)

    def test_receive_partial_marks_partially_received(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        line = po.lines.get()
        receive_po(po, receipts=[{"line": line.id, "quantity": 10}], user=self.manager)
        po.refresh_from_db()
        line.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.assertEqual(line.quantity_received, 10)
        self.assertEqual(self.product.quantity_on_hand, 18)

    def test_receiving_the_remainder_completes_the_po(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        line = po.lines.get()
        receive_po(po, receipts=[{"line": line.id, "quantity": 10}], user=self.manager)
        # Second receipt with no explicit receipts takes all remaining.
        receive_po(po, user=self.manager)
        po.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(self.product.quantity_on_hand, 68)

    def test_cannot_receive_more_than_outstanding(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        submit_po(po)
        line = po.lines.get()
        with self.assertRaises(ValidationError):
            receive_po(
                po, receipts=[{"line": line.id, "quantity": 999}], user=self.manager
            )

    def test_cannot_receive_a_draft(self):
        po = create_reorder_po(product=self.product, user=self.manager)
        with self.assertRaises(ValidationError):
            receive_po(po, user=self.manager)


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locking")
class ConcurrentReceiptTests(TransactionTestCase):
    reset_sequences = True

    def test_duplicate_full_receipt_has_one_stock_effect(self):
        manager = User.objects.create_user(
            username="receipt-race-manager",
            password="x",
            role=User.Role.MANAGER,
        )
        product = Product.objects.create(
            sku="PO-RACE", name="Receipt Race", reorder_quantity=5
        )
        record_movement(
            product=product,
            quantity_delta=10,
            reason=StockMovement.Reason.INITIAL,
            user=manager,
        )
        supplier = Supplier.objects.create(
            code="SUP-RACE", name="Race Supplier", default_lead_time_days=3
        )
        link = SupplierProduct.objects.create(
            supplier=supplier,
            product=product,
            is_preferred=True,
        )
        SupplierPriceTier.objects.create(
            supplier_product=link,
            min_quantity=1,
            unit_price=Decimal("25.00"),
        )
        po = create_reorder_po(product=product, user=manager, quantity=5)
        submit_po(po)
        barrier = Barrier(2)

        def receive_once(_):
            try:
                local_po = PurchaseOrder.objects.get(pk=po.pk)
                barrier.wait(timeout=10)
                return receive_po(local_po, user=manager).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            po_ids = list(pool.map(receive_once, range(2)))

        product.refresh_from_db()
        po.refresh_from_db()
        line = po.lines.get()
        self.assertEqual(po_ids, [po.id, po.id])
        self.assertEqual(product.quantity_on_hand, 15)
        self.assertEqual(line.quantity_received, 5)
        self.assertEqual(
            StockMovement.objects.filter(
                product=product,
                purchase_order=po,
                reason=StockMovement.Reason.PURCHASE_RECEIPT,
            ).count(),
            1,
        )
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
