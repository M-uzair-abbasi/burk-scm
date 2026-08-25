"""Deterministic opaque review links for demo and contract tests."""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.utils.crypto import salted_hmac

from .base import ReviewLinkProvider

SIGNING_SALT = "burk-scm.review-link.v1"


class SimulatedReviewLinkProvider(ReviewLinkProvider):
    name = "simulated"

    def health(self) -> dict:
        return {"ok": True, "mode": "simulated", "adapter": self.name}

    def build(self, order, *, event_key: str) -> str:
        # Only an HMAC digest is exposed. The source/external identifiers and
        # event key are inputs, never token payload, so the URL cannot leak them.
        opaque_key = salted_hmac(
            SIGNING_SALT,
            f"{order.channel}|{order.external_id}|{event_key}",
            secret=settings.SECRET_KEY,
        ).hexdigest()
        token = signing.Signer(salt=SIGNING_SALT).sign(opaque_key)
        query = urlencode({"token": token})
        return f"{settings.BURK_REVIEW_BASE_URL.rstrip('/')}?{query}"
