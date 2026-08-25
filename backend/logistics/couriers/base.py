"""Courier adapter interface. Mirrors orders/connectors and notifications/channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import ClassVar


@dataclass(frozen=True)
class BookingRequest:
    order_id: int
    order_reference: str
    external_order_id: str
    recipient_name: str
    phone: str
    address_line1: str
    address_line2: str = ""
    city: str = ""
    province: str = ""
    postal_code: str = ""
    country: str = "PK"
    item_count: int = 0
    currency: str = "PKR"
    declared_value: Decimal = Decimal("0.00")
    cod_amount: Decimal = Decimal("0.00")
    payment_mode: str = "prepaid"
    service_type: str = "standard"
    pickup_account: str = ""
    customer_instructions: str = ""
    weight_kg: Decimal = Decimal("0.000")
    length_cm: Decimal = Decimal("0.00")
    width_cm: Decimal = Decimal("0.00")
    height_cm: Decimal = Decimal("0.00")
    idempotency_key: str = ""

    _DECIMAL_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "declared_value",
        "cod_amount",
        "weight_kg",
        "length_cm",
        "width_cm",
        "height_cm",
    })

    def to_payload(self) -> dict:
        payload = dict(self.__dict__)
        for field_name in self._DECIMAL_FIELDS:
            payload[field_name] = format(payload[field_name], "f")
        return payload

    @classmethod
    def from_payload(cls, payload: dict) -> "BookingRequest":
        values = dict(payload)
        for field_name in cls._DECIMAL_FIELDS:
            values[field_name] = Decimal(str(values.get(field_name, "0")))
        values["order_id"] = int(values["order_id"])
        values["item_count"] = int(values.get("item_count", 0))
        return cls(**values)


@dataclass
class BookingResult:
    courier: str
    tracking_number: str
    provider_booking_id: str = ""
    label_reference: str = ""
    label_url: str = ""
    raw: dict = field(default_factory=dict)


class CourierAdapter:
    name: str = ""

    def health(self) -> dict:
        return {"ok": False, "mode": "unknown"}

    def book(self, request: BookingRequest) -> BookingResult:
        """Book one validated immutable request and return tracking details."""
        raise NotImplementedError
