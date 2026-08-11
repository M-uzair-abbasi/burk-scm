"""Placeholder for a real Leopard Courier API integration.

The documented drop-in for production, same role as orders/connectors/live_daraz.py.
To activate: implement book() as a signed POST to Leopard's booking endpoint
(consignment creation), provide LEOPARD_API_KEY / LEOPARD_API_PASSWORD via
settings, and register this class instead of SimulatedCourierAdapter in
couriers/__init__.py. TCS/Trax/M&P would each get their own live_*.py following
the same shape — this one file stands in for that pattern.
"""

from __future__ import annotations

from .base import BookingResult, CourierAdapter


class LiveLeopardAdapter(CourierAdapter):
    name = "leopard"

    def book(self, order) -> BookingResult:
        raise NotImplementedError(
            "Live Leopard Courier integration requires LEOPARD_API_KEY and "
            "LEOPARD_API_PASSWORD. Implement the signed booking POST here."
        )
