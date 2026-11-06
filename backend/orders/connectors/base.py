"""Channel connector interface.

A connector turns one sales channel's own order feed into the channel-agnostic
NormalizedOrder the ingestion service consumes. fetch() and normalize() are kept
separate on purpose: a real Daraz Seller Center API client only has to reimplement
fetch() (the network call), leaving normalize() and the whole ingestion core
untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


def normalize_country_code(value, *, default: str = "PK") -> str:
    """Return a carrier-safe ISO alpha-2 code for known source values."""
    text = str(value or "").strip().upper()
    aliases = {"PAKISTAN": "PK", "PAK": "PK", "PK": "PK"}
    if text in aliases:
        return aliases[text]
    if len(text) == 2 and text.isalpha():
        return text
    return default


@dataclass
class NormalizedLine:
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


@dataclass
class NormalizedOrder:
    channel: str
    external_id: str
    status: str = "pending"
    customer_name: str = ""
    customer_phone: str = ""
    customer_email: str = ""
    shipping_address: str = ""
    shipping_address_line1: str = ""
    shipping_address_line2: str = ""
    shipping_city: str = ""
    shipping_province: str = ""
    shipping_postal_code: str = ""
    shipping_country: str = "PK"
    customer_instructions: str = ""
    parcel_weight_kg: Decimal = Decimal("0.000")
    parcel_length_cm: Decimal = Decimal("0.00")
    parcel_width_cm: Decimal = Decimal("0.00")
    parcel_height_cm: Decimal = Decimal("0.00")
    cod_amount: Decimal = Decimal("0.00")
    payment_mode: str = "prepaid"
    shipping_service_type: str = "standard"
    pickup_account: str = ""
    currency: str = "PKR"
    subtotal: Decimal = Decimal("0.00")
    shipping_fee: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    placed_at: datetime | None = None
    lines: list[NormalizedLine] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)


class ChannelConnector:
    """Base class every channel implements.

    Subclasses set `channel` and implement fetch() (raw source records) and
    normalize() (one raw record -> NormalizedOrder).
    """

    channel: str = ""

    def health(self) -> dict:
        mode = "live" if ".live_" in self.__class__.__module__ else "simulated"
        try:
            records = self.fetch()
        except Exception as exc:  # noqa: BLE001 - readiness result
            return {
                "ok": False,
                "mode": mode,
                "error_class": exc.__class__.__name__,
            }
        return {"ok": True, "mode": mode, "records_available": len(records)}

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> NormalizedOrder:
        raise NotImplementedError

    def fetch_normalized(self) -> list[NormalizedOrder]:
        return [self.normalize(raw) for raw in self.fetch()]
