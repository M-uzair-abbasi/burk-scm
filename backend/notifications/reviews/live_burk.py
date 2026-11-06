"""Reserved adapter for Burk's real review-link API contract."""

from __future__ import annotations

from common.integrations import pending_live_health

from .base import ReviewLinkProvider


class LiveBurkReviewLinkProvider(ReviewLinkProvider):
    name = "live_burk"

    def health(self) -> dict:
        return pending_live_health(
            self.name,
            "BURK_REVIEW_API_BASE_URL",
            "BURK_REVIEW_API_TOKEN",
        )

    def build(self, order, *, event_key: str) -> str:
        raise NotImplementedError(
            "Live Burk review links require the approved storefront review API "
            "contract and credentials."
        )
