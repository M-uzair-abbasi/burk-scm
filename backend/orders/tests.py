"""Module 2 tests — the KPI-3 proof: no dropped or duplicated order records.

Two layers:
  * service-level tests drive exact NormalizedOrders through ingest_records so the
    dedup / reconciliation logic is pinned without depending on fixture contents;
  * integration tests run the real Burk/Daraz connectors against their fixtures to
    prove normalization and the end-to-end sync counts.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from fulfillment.models import PackScan
from fulfillment.services import complete_packing, record_scan, start_packing
from inventory.models import Product, StockMovement
from inventory.services import record_movement
from orders.connectors.base import ChannelConnector, NormalizedLine, NormalizedOrder
from orders.models import Channel, SalesOrder, SyncRun
from orders.serializers import SyncRunSerializer
from orders.services import (
    ingest_channel,
    ingest_records,
    queue_integrity,
    sync_all,
)

User = get_user_model()


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

    def test_resync_cannot_rewind_or_replace_locally_packed_order(self):
        product = Product.objects.create(
            sku="BRK-1001",
            name="Packed product",
            barcode="PACKED-1001",
        )
        replacement = Product.objects.create(
            sku="BRK-2002",
            name="Source replacement",
            barcode="PACKED-2002",
        )
        record_movement(
            product=product,
            quantity_delta=10,
            reason=StockMovement.Reason.INITIAL,
        )
        ingest_records("burk", [make_order("burk", "PACKED", sku=product.sku)])
        order = SalesOrder.objects.get(channel="burk", external_id="PACKED")
        original_line = order.lines.get()
        session = start_packing(order)
        scan = record_scan(session, product.barcode)
        complete_packing(session)

        ingest_records(
            "burk",
            [make_order("burk", "PACKED", sku=replacement.sku, status="pending")],
        )

        order.refresh_from_db()
        scan.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.PACKED)
        self.assertEqual(getattr(order, "source_status", None), SalesOrder.Status.PENDING)
        self.assertEqual(list(order.lines.values_list("id", flat=True)), [original_line.id])
        self.assertEqual(scan.line_id, original_line.id)

    def test_source_managed_order_continues_to_mirror_source_status(self):
        ingest_records("burk", [make_order("burk", "REMOTE", status="pending")])

        ingest_records("burk", [make_order("burk", "REMOTE", status="shipped")])

        order = SalesOrder.objects.get(channel="burk", external_id="REMOTE")
        self.assertEqual(order.status, SalesOrder.Status.SHIPPED)
        self.assertEqual(getattr(order, "source_status", None), SalesOrder.Status.SHIPPED)
        self.assertFalse(PackScan.objects.filter(session__order=order).exists())

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

    def test_normalization_failure_does_not_drop_valid_neighbour(self):
        class TwoRecordConnector(ChannelConnector):
            channel = Channel.BURK

            def fetch(self):
                return [
                    {"external_id": "GOOD"},
                    {"external_id": "BAD", "access_token": "must-not-leak"},
                ]

            def normalize(self, raw):
                if raw["external_id"] == "BAD":
                    raise ValueError("malformed quantity")
                return make_order(self.channel, raw["external_id"])

        with patch("orders.services.get_connector", return_value=TwoRecordConnector()):
            run = ingest_channel(Channel.BURK)

        self.assertEqual(run.fetched, 2)
        self.assertEqual(run.created, 1)
        self.assertEqual(run.failed, 1)
        self.assertFalse(run.ok)
        self.assertTrue(run.reconciled)
        self.assertTrue(SalesOrder.objects.filter(external_id="GOOD").exists())
        self.assertEqual(run.detail["errors"][0]["record_index"], 1)
        self.assertEqual(run.detail["errors"][0]["external_id"], "BAD")
        self.assertNotIn("must-not-leak", str(run.detail))
        self.assertEqual(SyncRunSerializer(run).data["detail"], run.detail)

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
        self.assertEqual(order.shipping_address_line1, "House 12, Street 4, DHA Phase 5")
        self.assertEqual(order.shipping_city, "Karachi")
        self.assertEqual(order.shipping_country, "PK")
        self.assertEqual(order.payment_mode, "prepaid")
        self.assertEqual(order.cod_amount, Decimal("0.00"))
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


class QueueIntegrityFailureTests(TestCase):
    def test_source_outage_and_zero_inspected_records_fail_integrity(self):
        with patch(
            "orders.services.get_connector",
            side_effect=RuntimeError("source unavailable"),
        ):
            result = queue_integrity()

        self.assertFalse(result["ok"])
        self.assertEqual(result["channels_checked"], 0)
        self.assertEqual(len(result["channel_errors"]), len(Channel.choices))
        self.assertEqual(result["inspected_records"], 0)

    def test_field_mismatch_fails_integrity(self):
        source = make_order("burk", "MISMATCH", qty=2, price="100.00")
        ingest_records("burk", [source])
        SalesOrder.objects.filter(channel="burk", external_id="MISMATCH").update(
            total=Decimal("999.00")
        )

        class OneOrderConnector(ChannelConnector):
            channel = Channel.BURK

            def fetch(self):
                return [source.raw_payload]

            def normalize(self, raw):
                return source

        with (
            patch.dict("orders.services.CONNECTORS", {"burk": OneOrderConnector}, clear=True),
            patch("orders.services.get_connector", return_value=OneOrderConnector()),
        ):
            result = queue_integrity()

        self.assertFalse(result["ok"])
        self.assertEqual(result["mismatched"], 1)
        self.assertEqual(result["mismatched_detail"][0]["external_id"], "MISMATCH")
        self.assertIn("total", result["mismatched_detail"][0]["fields"])


class SyncApiStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sync-manager",
            password="x",
            role=User.Role.MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _run(self, channel, *, ok):
        return SyncRun.objects.create(
            channel=channel,
            started_at=timezone.now(),
            finished_at=timezone.now(),
            fetched=1,
            created=1 if ok else 0,
            failed=0 if ok else 1,
            ok=ok,
            detail={} if ok else {"fetch_error": "unavailable"},
        )

    @patch("orders.views.build_summary", return_value={"integrity": {"ok": False}})
    @patch("orders.views.sync_all")
    def test_partial_sync_returns_207(self, sync_mock, _summary_mock):
        sync_mock.return_value = [
            self._run(Channel.BURK, ok=True),
            self._run(Channel.DARAZ, ok=False),
        ]

        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertEqual(response.status_code, 207)
        self.assertFalse(response.data["overall_ok"])

    @patch("orders.views.build_summary", return_value={"integrity": {"ok": False}})
    @patch("orders.views.sync_all")
    def test_all_channel_failure_returns_503(self, sync_mock, _summary_mock):
        sync_mock.return_value = [
            self._run(Channel.BURK, ok=False),
            self._run(Channel.DARAZ, ok=False),
        ]

        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.data["overall_ok"])

    @patch("orders.views.build_summary", return_value={"integrity": {"ok": True}})
    @patch("orders.views.sync_all")
    def test_successful_sync_returns_200_with_overall_ok(self, sync_mock, _summary_mock):
        sync_mock.return_value = [
            self._run(Channel.BURK, ok=True),
            self._run(Channel.DARAZ, ok=True),
        ]

        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get("overall_ok"))


class SyncAuthorizationTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="sync-operator",
            password="x",
            role=User.Role.OPERATOR,
        )
        self.manager = User.objects.create_user(
            username="sync-authorized-manager",
            password="x",
            role=User.Role.MANAGER,
        )
        self.client = APIClient()

    def test_anonymous_cannot_trigger_sync(self):
        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertIn(response.status_code, {401, 403})

    def test_operator_cannot_trigger_sync(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertEqual(response.status_code, 403)

    @patch("orders.views.build_summary", return_value={"integrity": {"ok": True}})
    @patch("orders.views.sync_all", return_value=[])
    def test_manager_can_trigger_sync(self, _sync_mock, _summary_mock):
        self.client.force_authenticate(self.manager)

        response = self.client.post("/api/orders/sync/", {}, format="json")

        self.assertNotEqual(response.status_code, 403)
