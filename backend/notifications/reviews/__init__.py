"""Review-destination adapter registry."""

from django.conf import settings

from common.integrations import require_demo_mode

from .base import ReviewLinkProvider
from .live_burk import LiveBurkReviewLinkProvider
from .simulated import SimulatedReviewLinkProvider

PROVIDERS = {
    "simulated": SimulatedReviewLinkProvider,
    "live_burk": LiveBurkReviewLinkProvider,
}


def get_review_link_provider(name: str | None = None) -> ReviewLinkProvider:
    name = name or settings.REVIEW_LINK_BACKEND
    if name == "simulated":
        require_demo_mode("review link")
    try:
        provider_class = PROVIDERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown review-link provider: {name!r}") from exc
    return provider_class()


__all__ = [
    "ReviewLinkProvider",
    "LiveBurkReviewLinkProvider",
    "SimulatedReviewLinkProvider",
    "PROVIDERS",
    "get_review_link_provider",
]
