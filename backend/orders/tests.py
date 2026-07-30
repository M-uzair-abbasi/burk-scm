"""Module 2 tests — the KPI-3 proof: no dropped or duplicated order records.

Two layers:
  * service-level tests drive exact NormalizedOrders through ingest_records so the
    dedup / reconciliation logic is pinned without depending on fixture contents;
  * integration tests run the real Burk/Daraz connectors against their fixtures to
    prove normalization and the end-to-end sync counts.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from inventory.models import Product
from orders.connectors.base import NormalizedLine, NormalizedOrder
from orders.models import Channel, SalesOrder, SyncRun
from orders.services import (
    ingest_channel,
    ingest_records,
    queue_integrity,
    sync_all,
)


def make_order(channel, external_id, *, sku="BRK-1001", qty=1, price="100.00",
               status="pending"):
    unit = Decimal(price)
    return NormalizedOrder(
        channel=channel,
        external_id=external_id,
        status=status,
        customer_name="Test Buyer",
        subtotal=unit * qty,
        total=unit * qty,
        lines=[
            NormalizedLine(
                sku=sku,
                product_name="Widget",
                quantity=qty,
                unit_price=unit,
                line_total=unit * qty,
            )
        ],
        raw_payload={"external_id": external_id},
    )


class IngestionServiceTests(TestCase):
    def test_first_sync_creates_orders_and_reconciles(self):
        run = ingest_records("burk", [make_order("burk", "A"), make_order("burk", "B")])
        self.assertEqual(run.fetched, 2)
        self.assertEqual(run.created, 2)
        self.assertEqual(run.updated, 0)
        self.assertEqual(run.duplicates_skipped, 0)
        self.assertEqual(run.failed, 0)
        self.assertTrue(run.reconciled)
        self.assertEqual(SalesOrder.objects.count(), 2)

    def test_resync_updates_never_duplicates(self):
        ingest_records("burk", [make_order("burk", "A"), make_order("burk", "B")])
        run = ingest_records(
            "burk",
            [make_order("burk", "A", status="shipped"), make_order("burk", "B")],
        )
        self.assertEqual(run.created, 0)
        self.assertEqual(run.updated, 2)
        self.assertTrue(run.reconciled)
        # Idempotent: still two rows, and the update took effect.
        self.assertEqual(SalesOrder.objects.count(), 2)
        self.assertEqual(
            SalesOrder.objects.get(channel="burk", external_id="A").status, "shipped"
        )

    def test_intra_batch_duplicate_is_skipped(self):
        run = ingest_records(
            "burk",
            [make_order("burk", "A"), make_order("burk", "A"), make_order("burk", "B")],
        )
        self.assertEqual(run.fetched, 3)
        self.assertEqual(run.created, 2)
        self.assertEqual(run.duplicates_skipped, 1)
        self.assertTrue(run.reconciled)
        self.assertEqual(SalesOrder.objects.count(), 2)

    def test_db_constraint_blocks_duplicate_key(self):
        ingest_records("burk", [make_order("burk", "A")])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SalesOrder.objects.create(channel="burk", external_id="A")

    def test_same_external_id_across_channels_is_distinct(self):
        ingest_records("burk", [make_order("burk", "SHARED")])
        ingest_records("daraz", [make_order("daraz", "SHARED")])
        self.assertEqual(SalesOrder.objects.count(), 2)
        self.assertEqual(SalesOrder.objects.filter(external_id="SHARED").count(), 2)

    def test_no_records_dropped(self):
        orders = [make_order("burk", f"ORD-{i}") for i in range(5)]
        ingest_records("burk", orders)
        stored = set(
            SalesOrder.objects.filter(channel="burk").values_list(
                "external_id", flat=True
            )
        )
        self.assertEqual(stored, {f"ORD-{i}" for i in range(5)})

    def test_reference_assigned_from_pk(self):
        ingest_records("burk", [make_order("burk", "A")])
        order = SalesOrder.objects.get(external_id="A")
        self.assertRegex(order.reference, r"^SO-\d{5}$")

    def test_product_resolved_by_sku(self):
        Product.objects.create(sku="BRK-1001", name="Cotton Kurta M")
        ingest_records(
            "burk",
            [
                make_order("burk", "MATCH", sku="BRK-1001"),
                make_order("burk", "MISS", sku="BRK-0000"),
            ],
        )
        matched = SalesOrder.objects.get(external_id="MATCH").lines.first()
        missed = SalesOrder.objects.get(external_id="MISS").lines.first()
        self.assertIsNotNone(matched.product)
        self.assertEqual(matched.product.sku, "BRK-1001")
        self.assertIsNone(missed.product)

    def test_failed_record_counted_but_run_still_reconciles(self):
        good = make_order("burk", "GOOD")
        bad = make_order("burk", "X" * 100)  # external_id exceeds varchar(64)
        run = ingest_records("burk", [good, bad])
        self.assertEqual(run.fetched, 2)
        self.assertEqual(run.created, 1)
        self.assertEqual(run.failed, 1)
        self.assertFalse(run.ok)
        self.assertTrue(run.reconciled)  # 1 + 0 + 0 + 1 == 2

    def test_fetch_error_is_logged_as_failed_run(self):
        run = ingest_records("daraz", [], fetch_error="connection refused")
        self.assertFalse(run.ok)
        self.assertEqual(run.fetched, 0)
        self.assertIn("fetch_error", run.detail)

    def test_syncrun_is_append_only(self):
        run = ingest_records("burk", [make_order("burk", "A")])
        run.created = 999
        with self.assertRaises(ValueError):
            run.save()


class ConnectorIntegrationTests(TestCase):
    """Runs the real connectors against their shipped fixtures."""

    def test_sync_all_returns_one_run_per_channel(self):
        runs = sync_all()
        self.assertEqual({r.channel for r in runs}, {Channel.BURK, Channel.DARAZ})

    def test_burk_feed_ingests_five_orders(self):
        run = ingest_channel("burk")
        self.assertEqual(run.fetched, 5)
        self.assertEqual(run.created, 5)
        self.assertEqual(run.duplicates_skipped, 0)
        self.assertTrue(run.reconciled)

    def test_daraz_feed_dedupes_the_repeated_order(self):
        run = ingest_channel("daraz")
        # Fixture ships 6 records, one an intra-batch duplicate of order 700100003.
        self.assertEqual(run.fetched, 6)
        self.assertEqual(run.created, 5)
        self.assertEqual(run.duplicates_skipped, 1)
        self.assertTrue(run.reconciled)
        self.assertEqual(SalesOrder.objects.filter(channel="daraz").count(), 5)

    def test_daraz_normalization_maps_fields(self):
        ingest_channel("daraz")
        order = SalesOrder.objects.get(channel="daraz", external_id="700100001")
        self.assertEqual(order.customer_name, "Ayesha Khan")
        self.assertEqual(order.status, "delivered")
        self.assertEqual(order.total, Decimal("3050.00"))  # 2900 + 150 shipping
        self.assertIn("Karachi", order.shipping_address)
        self.assertEqual(order.item_count, 1)

    def test_full_sync_has_zero_integrity_drift(self):
        sync_all()
        result = queue_integrity()
        self.assertEqual(result["dropped"], 0)
        self.assertEqual(result["duplicated"], 0)
        self.assertEqual(result["unique"], 10)  # 5 Burk + 5 unique Daraz
        self.assertTrue(result["ok"])

    def test_resync_all_keeps_queue_stable(self):
        sync_all()
        first = SalesOrder.objects.count()
        sync_all()
        self.assertEqual(SalesOrder.objects.count(), first)
