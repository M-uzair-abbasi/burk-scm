"""Contract for producing a customer-safe review destination."""

from __future__ import annotations


class ReviewLinkProvider:
    name: str = ""

    def health(self) -> dict:
        return {"ok": False, "mode": "unknown", "adapter": self.name}

    def build(self, order, *, event_key: str) -> str:
        raise NotImplementedError
