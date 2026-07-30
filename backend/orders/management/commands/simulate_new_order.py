"""Inject a brand-new simulated order so the next sync grows the queue by one.

For live demos: appends one fresh record to data/<channel>_injected.json, which
the connector merges into its feed. Each call adds a new unique id; running it
twice adds two orders. Delete the injected file to reset.
"""

import json

from django.core.management.base import BaseCommand

from orders.connectors._feed import DATA_DIR


class Command(BaseCommand):
    help = "Append a new simulated order to a channel feed (for live demos)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--channel",
            choices=["burk", "daraz"],
            default="daraz",
            help="Which channel to inject the order into.",
        )

    def handle(self, *args, **options):
        channel = options["channel"]
        path = DATA_DIR / f"{channel}_injected.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        n = len(existing)

        if channel == "burk":
            ref = f"BRK-ORD-{90001 + n}"
            record = {
                "order_ref": ref,
                "state": "pending",
                "buyer": {
                    "name": "Demo Walk-in",
                    "phone": "+923009990001",
                    "email": "demo@example.invalid",
                },
                "ship_to": "Demo Address, Lahore",
                "currency": "PKR",
                "amounts": {"subtotal": "1450.00", "shipping": "0.00", "total": "1450.00"},
                "placed_at": "2026-07-23T12:00:00+05:00",
                "items": [
                    {"sku": "BRK-1001", "title": "Cotton Kurta M", "qty": 1, "price": "1450.00"}
                ],
            }
            external = ref
        else:
            oid = 700190001 + n
            record = {
                "order_id": oid,
                "order_number": f"2042199{n + 1:05d}",
                "statuses": ["pending"],
                "customer_first_name": "Demo",
                "customer_last_name": "Buyer",
                "address_shipping": {
                    "phone": "+923009990002",
                    "address1": "Demo Plot 1",
                    "city": "Karachi",
                    "country": "Pakistan",
                },
                "price": "1875.00",
                "shipping_fee": "150.00",
                "created_at": "2026-07-23 12:00:00",
                "order_items": [
                    {
                        "sku": "BRK-2001",
                        "name": "Oxford Shirt M",
                        "quantity": 1,
                        "item_price": "1875.00",
                        "paid_price": "1875.00",
                    }
                ],
            }
            external = str(oid)

        existing.append(record)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Injected {channel} order {external}. "
                f"Run `manage.py sync_orders` (or click Sync now) to pull it in."
            )
        )
