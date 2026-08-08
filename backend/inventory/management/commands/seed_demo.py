"""Populate a realistic demo dataset.

The edge cases here are deliberate. Seed data made only of healthy products
lets the test suite pass while the live demo breaks on the first odd row, so
this includes: a product sitting exactly on its threshold, one with no
threshold at all, one already out of stock, one with no supplier, and one with
several price tiers.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from inventory.models import Category, Product, StockMovement
from inventory.services import record_movement
from fulfillment.models import PackingSession, PackScan
from orders.models import SalesOrder, SalesOrderLine, SyncRun
from orders.services import sync_all
from purchasing.models import PurchaseOrder, PurchaseOrderLine
from suppliers.models import Supplier, SupplierPriceTier, SupplierProduct

User = get_user_model()

DEMO_PASSWORD = "burkdemo123"

CATEGORIES = ["Kurtas", "Shirts", "Trousers", "Accessories"]

# (sku, name, category, barcode, safety, reorder, cost, opening_stock)
PRODUCTS = [
    # Sits exactly on the threshold — must read as LOW (boundary case).
    ("BRK-1001", "Cotton Kurta M", "Kurtas", "8964000000015", 20, 50, "1450.00", 20),
    # Comfortably stocked — must NOT read as low.
    ("BRK-1002", "Cotton Kurta L", "Kurtas", "8964000000022", 20, 50, "1450.00", 64),
    # One above the threshold — the off-by-one guard.
    ("BRK-1003", "Linen Kurta M", "Kurtas", "8964000000039", 15, 40, "2100.00", 16),
    # Below threshold — the ordinary low-stock case.
    ("BRK-2001", "Oxford Shirt M", "Shirts", "8964000000046", 25, 60, "1875.00", 8),
    # Out of stock entirely.
    ("BRK-2002", "Oxford Shirt L", "Shirts", "8964000000053", 25, 60, "1875.00", 0),
    # No threshold set — 0 <= 0 must NOT flood the low-stock panel.
    ("BRK-3001", "Chino Trouser 32", "Trousers", "8964000000060", 0, 0, "2400.00", 12),
    # No supplier linked — Reorder must degrade gracefully, not 500.
    ("BRK-4001", "Leather Belt", "Accessories", "8964000000077", 10, 30, "950.00", 4),
    # No barcode at all — proves multiple NULLs coexist under a unique index.
    ("BRK-4002", "Silk Pocket Square", "Accessories", None, 5, 20, "600.00", 30),
    ("BRK-4003", "Cufflinks Pair", "Accessories", None, 5, 20, "1200.00", 18),
]

SUPPLIERS = [
    ("SUP-LHR-01", "Lahore Textile Mills", "Imran Qureshi", "orders@example.invalid",
     "+923001234501", "Lahore", 7, "30 days net"),
    ("SUP-KHI-01", "Karachi Fabric House", "Sana Iqbal", "sales@example.invalid",
     "+923001234502", "Karachi", 12, "50% advance"),
    ("SUP-FSD-01", "Faisalabad Weavers", "Tariq Mehmood", "info@example.invalid",
     "+923001234503", "Faisalabad", 5, "Cash on delivery"),
]

# product_sku -> (supplier_code, is_preferred, [(min_qty, unit_price)])
SUPPLY_LINKS = {
    "BRK-1001": ("SUP-LHR-01", True, [(1, "1500.00"), (50, "1380.00"), (200, "1290.00")]),
    "BRK-1002": ("SUP-LHR-01", True, [(1, "1500.00"), (50, "1380.00")]),
    "BRK-1003": ("SUP-FSD-01", True, [(1, "2200.00"), (40, "2050.00")]),
    "BRK-2001": ("SUP-KHI-01", True, [(1, "1950.00"), (60, "1820.00"), (150, "1740.00")]),
    "BRK-2002": ("SUP-KHI-01", True, [(1, "1950.00"), (60, "1820.00")]),
    "BRK-3001": ("SUP-FSD-01", True, [(1, "2500.00")]),
    "BRK-4002": ("SUP-KHI-01", True, [(1, "640.00"), (20, "580.00")]),
    "BRK-4003": ("SUP-LHR-01", True, [(1, "1250.00")]),
    # BRK-4001 intentionally absent — the no-supplier path.
}


class Command(BaseCommand):
    help = "Create demo users, categories, products, suppliers and opening stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            # Order matters: StockMovement, PurchaseOrderLine and PurchaseOrder
            # all hold PROTECT/references to Product and Supplier, so they must
            # be cleared before the rows they point at.
            StockMovement.objects.all().delete()
            PurchaseOrderLine.objects.all().delete()
            PurchaseOrder.objects.all().delete()
            # PackingSession PROTECTs its SalesOrder, so clear packing first.
            PackScan.objects.all().delete()
            PackingSession.objects.all().delete()
            SalesOrderLine.objects.all().delete()
            SalesOrder.objects.all().delete()
            SyncRun.objects.all().delete()
            SupplierPriceTier.objects.all().delete()
            SupplierProduct.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            Supplier.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing demo data removed."))

        manager = self._user("manager", User.Role.MANAGER, staff=True)
        self._user("operator", User.Role.OPERATOR)

        categories = {
            name: Category.objects.get_or_create(
                name=name, defaults={"slug": slugify(name)}
            )[0]
            for name in CATEGORIES
        }

        products = {}
        for sku, name, cat, barcode, safety, reorder, cost, opening in PRODUCTS:
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": categories[cat],
                    "barcode": barcode,
                    "safety_stock": safety,
                    "reorder_quantity": reorder,
                    "cost_price": Decimal(cost),
                },
            )
            products[sku] = product
            if created and opening:
                record_movement(
                    product=product,
                    quantity_delta=opening,
                    reason=StockMovement.Reason.INITIAL,
                    user=manager,
                    note="Opening balance (demo seed).",
                )

        suppliers = {}
        for code, name, contact, email, phone, city, lead, terms in SUPPLIERS:
            suppliers[code] = Supplier.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "contact_person": contact,
                    "email": email,
                    "phone": phone,
                    "city": city,
                    "default_lead_time_days": lead,
                    "payment_terms": terms,
                },
            )[0]

        for sku, (supplier_code, preferred, tiers) in SUPPLY_LINKS.items():
            link, _ = SupplierProduct.objects.get_or_create(
                supplier=suppliers[supplier_code],
                product=products[sku],
                defaults={
                    "supplier_sku": f"{supplier_code.split('-')[1]}-{sku[-4:]}",
                    "is_preferred": preferred,
                },
            )
            for min_qty, price in tiers:
                SupplierPriceTier.objects.get_or_create(
                    supplier_product=link,
                    min_quantity=min_qty,
                    defaults={"unit_price": Decimal(price)},
                )

        low = Product.objects.low_stock().count()
        out = Product.objects.out_of_stock().count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Product.objects.count()} products, "
                f"{Supplier.objects.count()} suppliers. "
                f"{low} low-stock, {out} out-of-stock."
            )
        )
        # Pull the simulated channel feeds so the order queue isn't empty on
        # first load. Idempotent: re-running seed re-syncs without duplicating.
        runs = sync_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {SalesOrder.objects.count()} orders from "
                f"{len(runs)} channel(s): {', '.join(r.channel for r in runs)}."
            )
        )
        self.stdout.write(f"Logins: manager / operator  (password: {DEMO_PASSWORD})")

    def _user(self, username, role, staff=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "is_staff": staff,
                "is_superuser": staff,
                "email": f"{username}@example.invalid",
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        return user
