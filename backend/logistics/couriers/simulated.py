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

import hashlib

from ..models import Courier
from .base import BookingRequest, BookingResult, CourierAdapter

_PREFIX = {
    Courier.LEOPARD: "LCS",
    Courier.TCS: "TCS",
    Courier.TRAX: "TRX",
    Courier.MNP: "MNP",
}
_ROTATION = [Courier.LEOPARD, Courier.TCS, Courier.TRAX, Courier.MNP]


class SimulatedCourierAdapter(CourierAdapter):
    name = "simulated"

    def health(self) -> dict:
        return {"ok": True, "mode": "simulated", "adapter": self.name}

    def book(self, request: BookingRequest) -> BookingResult:
        courier = _ROTATION[request.order_id % len(_ROTATION)]
        suffix = hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()[:16].upper()
        tracking_number = f"{_PREFIX[courier]}{suffix}"
        return BookingResult(
            courier=courier,
            tracking_number=tracking_number,
            provider_booking_id=f"SIM-{suffix}",
            label_reference=f"SIM-LABEL-{suffix}",
            label_url=f"https://labels.example.invalid/{tracking_number}.pdf",
            raw={
                "courier": courier,
                "tracking_number": tracking_number,
                "provider_booking_id": f"SIM-{suffix}",
                "order_reference": request.order_reference,
                "destination_city": request.city,
                "idempotency_key": request.idempotency_key,
                "simulated": True,
            },
        )
