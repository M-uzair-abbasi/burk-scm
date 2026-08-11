"""Simulated multi-courier booking.

No real Leopard/TCS/Trax/M&P credentials exist in this environment, so this
adapter reproduces the shape a real courier API's booking response has — a
courier-specific tracking number format, a label URL, a raw response payload —
without calling out anywhere. Courier selection is deterministic (by order id)
so a demo or test can reason about which courier a given order lands on.
live_leopard.py is the documented drop-in for one real integration; the other
three couriers would follow the same shape.
"""

from __future__ import annotations

import uuid

from ..models import Courier
from .base import BookingResult, CourierAdapter

_PREFIX = {
    Courier.LEOPARD: "LCS",
    Courier.TCS: "TCS",
    Courier.TRAX: "TRX",
    Courier.MNP: "MNP",
}
_ROTATION = [Courier.LEOPARD, Courier.TCS, Courier.TRAX, Courier.MNP]


class SimulatedCourierAdapter(CourierAdapter):
    name = "simulated"

    def book(self, order) -> BookingResult:
        courier = _ROTATION[order.id % len(_ROTATION)]
        tracking_number = f"{_PREFIX[courier]}{uuid.uuid4().int % 10**9:09d}"
        return BookingResult(
            courier=courier,
            tracking_number=tracking_number,
            label_url=f"https://labels.example.invalid/{tracking_number}.pdf",
            raw={
                "courier": courier,
                "tracking_number": tracking_number,
                "order_reference": order.reference,
                "destination": order.shipping_address,
                "simulated": True,
            },
        )
