from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import TestCase, TransactionTestCase

from .models import Product, StockMovement
from .services import ledger_balance, record_movement

User = get_user_model()


def make_product(sku="BRK-1001", *, safety=20, reorder=50, **kwargs):
    return Product.objects.create(
        sku=sku,
        name=kwargs.pop("name", "Cotton Kurta M"),
        safety_stock=safety,
        reorder_quantity=reorder,
        **kwargs,
    )


class RecordMovementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ayesha", password="x")
        self.product = make_product()

    def test_movement_updates_ledger_and_cache_together(self):
        record_movement(
            product=self.product,
            quantity_delta=30,
            reason=StockMovement.Reason.INITIAL,
            user=self.user,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, 30)
        self.assertEqual(ledger_balance(self.product), 30)

    def test_cache_always_equals_ledger_after_many_movements(self):
        for delta in (100, -30, -5, 12, -7):
            record_movement(
                product=self.product,
                quantity_delta=delta,
                reason=StockMovement.Reason.ADJUSTMENT,
                user=self.user,
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, 70)
        self.assertEqual(ledger_balance(self.product), 70)

    def test_caller_instance_is_not_left_stale(self):
        record_movement(
            product=self.product,
            quantity_delta=8,
            reason=StockMovement.Reason.INITIAL,
        )
        # Without refresh_from_db: the passed-in instance must already agree.
        self.assertEqual(self.product.quantity_on_hand, 8)

    def test_zero_delta_rejected(self):
        with self.assertRaises(ValidationError):
            record_movement(
                product=self.product,
                quantity_delta=0,
                reason=StockMovement.Reason.ADJUSTMENT,
            )

    def test_oversell_refused_and_nothing_written(self):
        record_movement(
            product=self.product,
            quantity_delta=5,
            reason=StockMovement.Reason.INITIAL,
        )
        with self.assertRaises(ValidationError):
            record_movement(
                product=self.product,
                quantity_delta=-6,
                reason=StockMovement.Reason.SALE,
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, 5)
        # The refused movement must not have been recorded.
        self.assertEqual(self.product.movements.count(), 1)

    def test_manager_can_correct_below_zero_with_allow_negative(self):
        record_movement(
            product=self.product,
            quantity_delta=3,
            reason=StockMovement.Reason.INITIAL,
        )
        record_movement(
            product=self.product,
            quantity_delta=-10,
            reason=StockMovement.Reason.ADJUSTMENT,
            allow_negative=True,
            note="Recount: opening balance was overstated.",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, -7)
        self.assertEqual(ledger_balance(self.product), -7)

    def test_failed_movement_rolls_back_both_writes(self):
        record_movement(
            product=self.product,
            quantity_delta=10,
            reason=StockMovement.Reason.INITIAL,
        )
        try:
            with transaction.atomic():
                record_movement(
                    product=self.product,
                    quantity_delta=5,
                    reason=StockMovement.Reason.RETURN,
                )
                raise RuntimeError("caller blows up after the movement")
        except RuntimeError:
            pass

        self.product.refresh_from_db()
        # Neither the ledger row nor the cache survives the rollback.
        self.assertEqual(self.product.quantity_on_hand, 10)
        self.assertEqual(ledger_balance(self.product), 10)
        self.assertEqual(self.product.movements.count(), 1)

    def test_movement_is_append_only(self):
        movement = record_movement(
            product=self.product,
            quantity_delta=10,
            reason=StockMovement.Reason.INITIAL,
        )
        movement.quantity_delta = 999
        with self.assertRaises(ValueError):
            movement.save()

    def test_zero_delta_blocked_at_database_level(self):
        # Belt and braces: even bypassing the service, the DB refuses.
        with self.assertRaises(IntegrityError):
            StockMovement.objects.create(
                product=self.product,
                quantity_delta=0,
                reason=StockMovement.Reason.ADJUSTMENT,
            )


class LowStockBoundaryTests(TestCase):
    """The alert boundary. These are the cases that break demos."""

    def _at(self, sku, on_hand, safety):
        product = make_product(sku=sku, safety=safety)
        if on_hand:
            record_movement(
                product=product,
                quantity_delta=on_hand,
                reason=StockMovement.Reason.INITIAL,
            )
        return product

    def test_exactly_at_threshold_is_low(self):
        self._at("AT-THRESHOLD", on_hand=20, safety=20)
        self.assertEqual(
            list(Product.objects.low_stock().values_list("sku", flat=True)),
            ["AT-THRESHOLD"],
        )

    def test_one_above_threshold_is_not_low(self):
        self._at("ABOVE", on_hand=21, safety=20)
        self.assertFalse(Product.objects.low_stock().exists())

    def test_untracked_product_with_zero_threshold_is_not_low(self):
        # 0 <= 0 is true; without the guard this floods the panel.
        self._at("UNTRACKED", on_hand=0, safety=0)
        self.assertFalse(Product.objects.low_stock().exists())
        self.assertTrue(Product.objects.out_of_stock().exists())

    def test_inactive_product_is_excluded(self):
        product = self._at("GONE", on_hand=1, safety=20)
        product.is_active = False
        product.save(update_fields=["is_active"])
        self.assertFalse(Product.objects.low_stock().exists())

    def test_property_and_queryset_agree(self):
        for sku, on_hand, safety in [
            ("A", 20, 20),
            ("B", 21, 20),
            ("C", 0, 0),
            ("D", 5, 20),
        ]:
            self._at(sku, on_hand=on_hand, safety=safety)

        from_queryset = set(Product.objects.low_stock().values_list("sku", flat=True))
        from_property = {p.sku for p in Product.objects.all() if p.is_low_stock}
        # Three code paths, one answer — the UI badge depends on this.
        self.assertEqual(from_queryset, from_property)
        self.assertEqual(from_queryset, {"A", "D"})


class BarcodeTests(TestCase):
    def test_multiple_products_may_have_no_barcode(self):
        # Postgres allows many NULLs in a unique index but only one ''.
        make_product(sku="NB-1", barcode=None)
        make_product(sku="NB-2", barcode=None)
        self.assertEqual(Product.objects.filter(barcode__isnull=True).count(), 2)

    def test_duplicate_barcode_is_refused(self):
        make_product(sku="BC-1", barcode="8964000112233")
        with self.assertRaises(IntegrityError):
            make_product(sku="BC-2", barcode="8964000112233")

    def test_clean_normalises_blank_barcode_to_null(self):
        product = Product(sku="BLANK-1", name="x", barcode="")
        product.clean()
        self.assertIsNone(product.barcode)


class ConcurrentMovementTests(TransactionTestCase):
    """select_for_update must serialise concurrent writers.

    TransactionTestCase (not TestCase): threads need real committed rows, and
    TestCase's wrapping transaction would hide them from other connections.
    """

    def test_concurrent_movements_do_not_lose_updates(self):
        product = make_product(sku="RACE-1", safety=0)
        record_movement(
            product=product,
            quantity_delta=100,
            reason=StockMovement.Reason.INITIAL,
        )

        def sell():
            try:
                record_movement(
                    product=product,
                    quantity_delta=-1,
                    reason=StockMovement.Reason.SALE,
                )
            finally:
                # Threads must not leak connections.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: sell(), range(20)))

        product.refresh_from_db()
        # Without the row lock, a read-modify-write race loses some of these.
        self.assertEqual(product.quantity_on_hand, 80)
        self.assertEqual(ledger_balance(product), 80)
        self.assertEqual(product.movements.count(), 21)
