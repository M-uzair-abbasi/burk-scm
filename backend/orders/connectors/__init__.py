"""Environment-selected order-source connector registry."""

from django.conf import settings

from common.integrations import require_demo_mode

from .base import ChannelConnector, NormalizedLine, NormalizedOrder
from .burk import BurkConnector
from .daraz import DarazConnector
from .live_burk import LiveBurkConnector
from .live_daraz import LiveDarazConnector

# Kept as the canonical required-channel map and fixture registry for existing
# ingestion/reconciliation callers and demo-reset discovery.
CONNECTORS = {
    "burk": BurkConnector,
    "daraz": DarazConnector,
}
LIVE_CONNECTORS = {
    "burk": LiveBurkConnector,
    "daraz": LiveDarazConnector,
}

__all__ = [
    "ChannelConnector",
    "NormalizedLine",
    "NormalizedOrder",
    "BurkConnector",
    "DarazConnector",
    "LiveBurkConnector",
    "LiveDarazConnector",
    "CONNECTORS",
    "LIVE_CONNECTORS",
    "get_connector",
]


def get_connector(channel: str) -> ChannelConnector:
    backend = settings.ORDER_CONNECTOR_BACKENDS.get(channel, "")
    if backend == "fixture":
        require_demo_mode(f"orders.{channel}")
        registry = CONNECTORS
    elif backend == "live":
        registry = LIVE_CONNECTORS
    else:
        raise ValueError(
            f"Unknown backend {backend!r} for order channel {channel!r}."
        )
    try:
        connector_cls = registry[channel]
    except KeyError as exc:
        raise ValueError(f"Unknown channel: {channel!r}") from exc
    return connector_cls()
