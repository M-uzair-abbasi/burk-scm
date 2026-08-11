"""Notification channel interface.

Mirrors orders/connectors: a channel only has to implement send(), the rest of
the dispatch pipeline (ledger row, status, latency) is channel-agnostic. Swapping
the simulated WhatsApp channel for a real Cloud API client is a one-line change
in CHANNELS below.
"""

from __future__ import annotations


class NotificationChannel:
    """Base class every delivery channel implements.

    send() must raise on failure (services.dispatch() catches it and records
    status=FAILED) and may return a small dict of provider detail to merge into
    the Notification's payload (e.g. a provider message id).
    """

    name: str = ""

    def send(self, notification) -> dict:
        raise NotImplementedError
