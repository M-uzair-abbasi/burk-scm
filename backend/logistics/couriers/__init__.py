"""Courier registry. Mirrors orders/connectors and notifications/channels."""

from .base import BookingResult, CourierAdapter
from .simulated import SimulatedCourierAdapter

CARRIERS = {
    "simulated": SimulatedCourierAdapter,
}

__all__ = ["BookingResult", "CourierAdapter", "CARRIERS", "get_carrier"]


def get_carrier(name: str = "simulated") -> CourierAdapter:
    try:
        carrier_cls = CARRIERS[name]
    except KeyError:
        raise ValueError(f"Unknown courier adapter: {name!r}")
    return carrier_cls()
