"""Courier adapter interface. Mirrors orders/connectors and notifications/channels."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BookingResult:
    courier: str
    tracking_number: str
    label_url: str = ""
    raw: dict = field(default_factory=dict)


class CourierAdapter:
    name: str = ""

    def book(self, order) -> BookingResult:
        """Book a shipment for `order` and return its tracking details."""
        raise NotImplementedError
