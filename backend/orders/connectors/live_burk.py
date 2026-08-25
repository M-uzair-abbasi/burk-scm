"""Reserved live connector for Burk's authoritative order interface."""

from __future__ import annotations

from common.integrations import pending_live_health

from .burk import BurkConnector


class LiveBurkConnector(BurkConnector):
    channel = "burk"

    def health(self) -> dict:
        return pending_live_health(
            "burk",
            "BURK_ORDER_API_BASE_URL",
            "BURK_ORDER_API_TOKEN",
        )

    def fetch(self) -> list[dict]:
        raise NotImplementedError(
            "Live Burk order ingestion requires the approved REST/webhook/read-"
            "model contract and staging credentials."
        )
