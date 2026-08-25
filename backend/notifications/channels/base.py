"""Notification channel interface.

Mirrors orders/connectors: a channel only has to implement send(), the rest of
the dispatch pipeline (ledger row, status, latency) is channel-agnostic. Swapping
the simulated WhatsApp channel for a real Cloud API client is a one-line change
in CHANNELS below.
"""

from __future__ import annotations


class NotificationChannel:
    """Base class every delivery channel implements.

    send() must raise on failure. The durable worker catches it, records retry
    or terminal failure state, and may merge returned provider detail into the
    Notification payload (for example a provider message id).
    """

    name: str = ""

    def health(self) -> dict:
        return {"ok": False, "mode": "unknown"}

    def send(self, notification) -> dict:
        raise NotImplementedError
