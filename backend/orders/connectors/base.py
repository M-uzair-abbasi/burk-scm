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

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> NormalizedOrder:
        raise NotImplementedError

    def fetch_normalized(self) -> list[NormalizedOrder]:
        return [self.normalize(raw) for raw in self.fetch()]
