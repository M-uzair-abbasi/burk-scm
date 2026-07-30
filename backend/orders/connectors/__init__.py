"""Channel connector registry.

CONNECTORS maps a channel key to its connector class. Swapping the simulated
DarazConnector for LiveDarazConnector here is the only change needed to go live —
the ingestion service, models and API are all channel-agnostic.
"""

from .base import ChannelConnector, NormalizedLine, NormalizedOrder
from .burk import BurkConnector
from .daraz import DarazConnector

CONNECTORS = {
    "burk": BurkConnector,
    "daraz": DarazConnector,
}

__all__ = [
    "ChannelConnector",
    "NormalizedLine",
    "NormalizedOrder",
    "BurkConnector",
    "DarazConnector",
    "CONNECTORS",
    "get_connector",
]


def get_connector(channel: str) -> ChannelConnector:
    try:
        connector_cls = CONNECTORS[channel]
    except KeyError:
        raise ValueError(f"Unknown channel: {channel!r}")
    return connector_cls()
