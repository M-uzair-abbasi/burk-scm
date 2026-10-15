"""Pull Burk's real WooCommerce product catalog into our inventory."""

from django.core.management.base import BaseCommand

from inventory.services import sync_products_from_woocommerce


class Command(BaseCommand):
    help = "Sync SKU'd WooCommerce products into the local catalog."

    def handle(self, *args, **options):
        result = sync_products_from_woocommerce()
        self.stdout.write(
            self.style.SUCCESS(
                f"fetched={result['fetched']} created={result['created']} "
                f"updated={result['updated']} unchanged={result['unchanged']} "
                f"skipped_no_sku={result['skipped_no_sku']} "
                f"failed={result['failed']}"
            )
        )
        for error in result["errors"]:
            self.stdout.write(self.style.ERROR(f"  {error['sku']}: {error['error']}"))
