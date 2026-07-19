"""Prove the cached stock quantity still matches the ledger, and repair it.

`--check` is the CI/demo mode: it reports drift and exits non-zero without
touching anything. Without the flag, cached values are rebuilt from the ledger,
which is authoritative.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import Product
from inventory.services import ledger_balance


class Command(BaseCommand):
    help = "Compare Product.quantity_on_hand against the StockMovement ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report drift and exit 1 without writing. Use in CI.",
        )

    def handle(self, *args, **options):
        check_only = options["check"]
        drifted = []

        for product in Product.objects.all().order_by("sku"):
            cached = product.quantity_on_hand
            actual = ledger_balance(product)
            if cached != actual:
                drifted.append((product, cached, actual))

        if not drifted:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No drift. {Product.objects.count()} product(s) agree with the ledger."
                )
            )
            return

        for product, cached, actual in drifted:
            self.stdout.write(
                self.style.WARNING(
                    f"{product.sku}: cached={cached} ledger={actual} drift={cached - actual:+d}"
                )
            )

        if check_only:
            # Non-zero exit so CI fails loudly.
            raise SystemExit(1)

        with transaction.atomic():
            for product, _cached, actual in drifted:
                product.quantity_on_hand = actual
                product.save(update_fields=["quantity_on_hand", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(f"Repaired {len(drifted)} product(s) from the ledger.")
        )
