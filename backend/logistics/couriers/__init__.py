"""Courier registry. Mirrors orders/connectors and notifications/channels."""

from django.conf import settings

from common.integrations import require_demo_mode

from .base import BookingRequest, BookingResult, CourierAdapter
from .simulated import SimulatedCourierAdapter
from .live_leopard import LiveLeopardAdapter

CARRIERS = {
    "simulated": SimulatedCourierAdapter,
    "live_leopard": LiveLeopardAdapter,
}

__all__ = [
    "BookingRequest",
    "BookingResult",
    "CourierAdapter",
    "LiveLeopardAdapter",
    "CARRIERS",
    "get_carrier",
]


def get_carrier(name: str | None = None) -> CourierAdapter:
    name = name or settings.COURIER_BACKEND
    if name == "simulated":
        require_demo_mode("courier")
    try:
        carrier_cls = CARRIERS[name]
    except KeyError:
        raise ValueError(f"Unknown courier adapter: {name!r}")
    return carrier_cls()
