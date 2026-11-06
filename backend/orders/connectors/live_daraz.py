"""Placeholder for the real Daraz Seller Center API connector.

This is the documented drop-in slot for production. When real credentials exist,
implement fetch() to call the Daraz Open Platform (sign the request with the app
secret, GET /orders/get for the window, GET /order/items/get per order) and
return the raw records. normalize() is inherited from DarazConnector unchanged —
the simulated feed is deliberately shaped like the real API response, so nothing
downstream of fetch() has to change.

To activate: register this class instead of DarazConnector in connectors/__init__.py
and provide DARAZ_APP_KEY / DARAZ_APP_SECRET / DARAZ_ACCESS_TOKEN via settings.
"""

from __future__ import annotations

from common.integrations import pending_live_health

from .daraz import DarazConnector


class LiveDarazConnector(DarazConnector):
    channel = "daraz"

    def health(self) -> dict:
        return pending_live_health(
            "daraz",
            "DARAZ_APP_KEY",
            "DARAZ_APP_SECRET",
            "DARAZ_ACCESS_TOKEN",
            "DARAZ_API_BASE_URL",
        )

    def fetch(self) -> list[dict]:
        raise NotImplementedError(
            "Live Daraz Seller Center integration requires real API credentials. "
            "Implement the signed /orders/get + /order/items/get calls here."
        )
