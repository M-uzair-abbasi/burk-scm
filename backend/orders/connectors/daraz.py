"""Daraz.pk marketplace connector (simulated feed).

The feed mimics the shape the Daraz Seller Center API returns: integer
`order_id`, a `statuses` list, split first/last customer names, a nested
`address_shipping`, `price`/`shipping_fee` money fields, naive
"YYYY-MM-DD HH:MM:SS" timestamps, and `order_items` with paid_price. normalize()
maps all of that onto the same NormalizedOrder that burk.py produces.

live_daraz.py shows where the real Seller Center HTTP client replaces fetch().
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from .base import ChannelConnector, NormalizedLine, NormalizedOrder
from ._feed import load_feed

# Daraz order statuses -> our normalized SalesOrder.Status values.
STATUS_MAP = {
    "pending": "pending",
    "ready_to_ship": "packed",
    "packed": "packed",
    "shipped": "shipped",
    "delivered": "delivered",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "returned": "returned",
    "failed": "cancelled",
}

_DARAZ_DT = "%Y-%m-%d %H:%M:%S"


def _parse_daraz_dt(value):
    """Daraz timestamps are naive local time; attach the active timezone."""
    if not value:
        return None
    naive = datetime.strptime(value, _DARAZ_DT)
    return timezone.make_aware(naive, timezone.get_current_timezone())


class DarazConnector(ChannelConnector):
    channel = "daraz"

    def fetch(self) -> list[dict]:
        return load_feed(self.channel)

    def normalize(self, raw: dict) -> NormalizedOrder:
        addr = raw.get("address_shipping", {})

        lines = []
        for item in raw.get("order_items", []):
            qty = int(item.get("quantity", 0))
            unit = Decimal(str(item.get("item_price", "0.00")))
            paid = item.get("paid_price")
            line_total = Decimal(str(paid)) if paid is not None else unit * qty
            lines.append(
                NormalizedLine(
                    sku=str(item.get("sku", "")),
                    product_name=str(item.get("name", "")),
                    quantity=qty,
                    unit_price=unit,
                    line_total=line_total,
                )
            )

        subtotal = Decimal(str(raw.get("price", "0.00")))
        shipping = Decimal(str(raw.get("shipping_fee", "0.00")))
        statuses = raw.get("statuses") or []
        status_src = str(statuses[-1]).lower() if statuses else ""

        address = ", ".join(
            part
            for part in (
                addr.get("address1", ""),
                addr.get("city", ""),
                addr.get("country", ""),
            )
            if part
        )
        full_name = " ".join(
            part
            for part in (
                raw.get("customer_first_name", ""),
                raw.get("customer_last_name", ""),
            )
            if part
        )

        return NormalizedOrder(
            channel=self.channel,
            external_id=str(raw["order_id"]),
            status=STATUS_MAP.get(status_src, "pending"),
            customer_name=full_name,
            customer_phone=addr.get("phone", ""),
            customer_email="",
            shipping_address=address,
            currency="PKR",
            subtotal=subtotal,
            shipping_fee=shipping,
            total=subtotal + shipping,
            placed_at=_parse_daraz_dt(raw.get("created_at")),
            lines=lines,
            raw_payload=raw,
        )
