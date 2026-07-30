"""Burk.pk storefront connector (simulated feed).

Burk is our own storefront, so its feed is clean snake_case with nested
buyer/amounts/items and ISO-8601 timestamps. Contrast with daraz.py, whose feed
is shaped differently — the point of two shapes is that normalize() does real
mapping work, not a pass-through.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.dateparse import parse_datetime

from .base import ChannelConnector, NormalizedLine, NormalizedOrder
from ._feed import load_feed

# Burk's storefront states -> our normalized SalesOrder.Status values.
STATUS_MAP = {
    "pending": "pending",
    "confirmed": "confirmed",
    "packed": "packed",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "returned": "returned",
}


class BurkConnector(ChannelConnector):
    channel = "burk"

    def fetch(self) -> list[dict]:
        return load_feed(self.channel)

    def normalize(self, raw: dict) -> NormalizedOrder:
        buyer = raw.get("buyer", {})
        amounts = raw.get("amounts", {})

        lines = []
        for item in raw.get("items", []):
            qty = int(item.get("qty", 0))
            price = Decimal(str(item.get("price", "0.00")))
            lines.append(
                NormalizedLine(
                    sku=str(item.get("sku", "")),
                    product_name=str(item.get("title", "")),
                    quantity=qty,
                    unit_price=price,
                    line_total=price * qty,
                )
            )

        return NormalizedOrder(
            channel=self.channel,
            external_id=str(raw["order_ref"]),
            status=STATUS_MAP.get(str(raw.get("state", "")).lower(), "pending"),
            customer_name=buyer.get("name", ""),
            customer_phone=buyer.get("phone", ""),
            customer_email=buyer.get("email", ""),
            shipping_address=raw.get("ship_to", ""),
            currency=raw.get("currency", "PKR"),
            subtotal=Decimal(str(amounts.get("subtotal", "0.00"))),
            shipping_fee=Decimal(str(amounts.get("shipping", "0.00"))),
            total=Decimal(str(amounts.get("total", "0.00"))),
            placed_at=parse_datetime(raw["placed_at"]) if raw.get("placed_at") else None,
            lines=lines,
            raw_payload=raw,
        )
