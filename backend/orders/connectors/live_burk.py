"""Live connector for Burk's real storefront: WooCommerce (dev.burk.pk staging).

Burk's real catalog mixes two fundamentally different product types: ordinary
stocked parts (electronics components, kits) that carry a WooCommerce SKU, and
made-to-order custom 3D prints that never do -- there is no physical barcode to
scan on an object that has not been printed yet. Module 3's pack verification
depends on a scannable SKU existing, and that design question (how to verify a
made-to-order line) has not been answered yet.

So, deliberately, for now: an order is only ingested if every line item carries
a WooCommerce SKU. Orders containing any un-SKU'd line are excluded in fetch()
itself and logged, not partially ingested with an unverifiable line mixed in.
This is a known, intentional scope limit, not the finished feature -- revisit
once pack verification for made-to-order items is designed.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from datetime import timezone as dt_timezone

from django.utils.dateparse import parse_datetime

from common.integrations import missing_setting_names
from common.woocommerce import fetch_all, ping

from .base import (
    ChannelConnector,
    NormalizedLine,
    NormalizedOrder,
    normalize_country_code,
)

logger = logging.getLogger(__name__)

# WooCommerce's own order statuses -> our normalized SalesOrder.Status values.
WOOCOMMERCE_STATUS_MAP = {
    "pending": "pending",
    "processing": "confirmed",
    "on-hold": "pending",
    "completed": "delivered",
    "cancelled": "cancelled",
    "refunded": "returned",
    "failed": "cancelled",
    "trash": "cancelled",
}

def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except InvalidOperation:
        return Decimal("0")


class LiveBurkConnector(ChannelConnector):
    channel = "burk"

    def health(self) -> dict:
        missing = missing_setting_names(
            "BURK_ORDER_API_BASE_URL",
            "BURK_ORDER_API_CONSUMER_KEY",
            "BURK_ORDER_API_CONSUMER_SECRET",
        )
        if missing:
            return {
                "ok": False,
                "mode": "live",
                "adapter": "burk",
                "missing_settings": missing,
                "detail": "missing_configuration",
            }
        # Not super().health() (== self.fetch()): that pulls every order over
        # the network on every health check. A health check only needs to
        # know the API is reachable.
        try:
            total = ping("orders")
        except Exception as exc:  # noqa: BLE001 - readiness result
            return {
                "ok": False,
                "mode": "live",
                "adapter": "burk",
                "error_class": exc.__class__.__name__,
            }
        return {
            "ok": True,
            "mode": "live",
            "adapter": "burk",
            "records_available": total,
        }

    def fetch(self) -> list[dict]:
        orders = fetch_all("orders")

        included, excluded = [], []
        for order in orders:
            (included if self._fully_skued(order) else excluded).append(order)
        if excluded:
            logger.info(
                "live_burk: excluded %d of %d orders with at least one line "
                "missing a WooCommerce SKU (made-to-order items, usually): %s",
                len(excluded),
                len(orders),
                [order.get("id") for order in excluded],
            )
        return included

    @staticmethod
    def _fully_skued(raw: dict) -> bool:
        items = raw.get("line_items") or []
        return bool(items) and all(
            str(item.get("sku") or "").strip() for item in items
        )

    @staticmethod
    def _parse_gmt(value):
        """WooCommerce's *_gmt fields are UTC but carry no offset -- attach
        it explicitly, since the sibling (non-_gmt) fields are site-local and
        parsing those naively produced a naive-datetime warning against this
        project's timezone-aware settings."""
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        return parsed.replace(tzinfo=dt_timezone.utc)

    def normalize(self, raw: dict) -> NormalizedOrder:
        billing = raw.get("billing") or {}
        shipping = raw.get("shipping") or billing

        lines = []
        for item in raw.get("line_items", []):
            quantity = int(item.get("quantity") or 0)
            line_total = _decimal(item.get("total"))
            unit_price = (line_total / quantity) if quantity else Decimal("0")
            lines.append(
                NormalizedLine(
                    sku=str(item["sku"]),
                    product_name=str(item.get("name", "")),
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

        payment_method = str(raw.get("payment_method") or "").lower()
        is_cod = payment_method == "cod"
        total = _decimal(raw.get("total"))
        shipping_fee = _decimal(raw.get("shipping_total"))

        shipping_address_line1 = str(shipping.get("address_1", ""))
        shipping_address_line2 = str(shipping.get("address_2", ""))
        shipping_address = " ".join(
            part for part in [shipping_address_line1, shipping_address_line2] if part
        )

        return NormalizedOrder(
            channel=self.channel,
            external_id=str(raw["id"]),
            status=WOOCOMMERCE_STATUS_MAP.get(
                str(raw.get("status", "")).lower(), "pending"
            ),
            customer_name=" ".join(
                part
                for part in [billing.get("first_name"), billing.get("last_name")]
                if part
            ),
            customer_phone=str(billing.get("phone", "")),
            customer_email=str(billing.get("email", "")),
            shipping_address=shipping_address,
            shipping_address_line1=shipping_address_line1,
            shipping_address_line2=shipping_address_line2,
            shipping_city=str(shipping.get("city", "")),
            shipping_province=str(shipping.get("state", "")),
            shipping_postal_code=str(shipping.get("postcode", "")),
            shipping_country=normalize_country_code(shipping.get("country", "PK")),
            customer_instructions=str(raw.get("customer_note", "")),
            cod_amount=total if is_cod else Decimal("0.00"),
            payment_mode="cod" if is_cod else "prepaid",
            currency=str(raw.get("currency", "PKR")),
            subtotal=total - shipping_fee,
            shipping_fee=shipping_fee,
            total=total,
            placed_at=self._parse_gmt(raw.get("date_created_gmt")),
            lines=lines,
            raw_payload=raw,
        )
