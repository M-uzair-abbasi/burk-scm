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

from .base import (
    ChannelConnector,
    NormalizedLine,
    NormalizedOrder,
    normalize_country_code,
)
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
        cod_amount = Decimal(str(raw.get("cod_amount", "0.00")))

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
            shipping_address_line1=str(addr.get("address1", "")),
            shipping_address_line2=str(addr.get("address2", "")),
            shipping_city=str(addr.get("city", "")),
            shipping_province=str(addr.get("province", addr.get("region", ""))),
            shipping_postal_code=str(addr.get("post_code", addr.get("postal_code", ""))),
            shipping_country=normalize_country_code(
                addr.get("country_code", addr.get("country", "PK"))
            ),
            customer_instructions=str(raw.get("customer_instructions", "")),
            parcel_weight_kg=Decimal(str(raw.get("parcel_weight_kg", "0.000"))),
            parcel_length_cm=Decimal(str(raw.get("parcel_length_cm", "0.00"))),
            parcel_width_cm=Decimal(str(raw.get("parcel_width_cm", "0.00"))),
            parcel_height_cm=Decimal(str(raw.get("parcel_height_cm", "0.00"))),
            cod_amount=cod_amount,
            payment_mode=str(
                raw.get("payment_method") or ("cod" if cod_amount > 0 else "prepaid")
            ).lower(),
            shipping_service_type=str(raw.get("shipping_service_type", "standard")),
            pickup_account=str(raw.get("pickup_account", "")),
            currency="PKR",
            subtotal=subtotal,
            shipping_fee=shipping,
            total=subtotal + shipping,
            placed_at=_parse_daraz_dt(raw.get("created_at")),
            lines=lines,
            raw_payload=raw,
        )
