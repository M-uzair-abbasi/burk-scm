"""Minimal shared client for Burk's WooCommerce REST API (dev.burk.pk staging).

Both the live order connector and the product-catalog sync need the same
authenticated, paginated GET against the WooCommerce v3 API. Kept in one place
so a change to auth or pagination only has to happen once.
"""

from __future__ import annotations

import requests
from django.conf import settings

PAGE_SIZE = 50
REQUEST_TIMEOUT_SECONDS = 30


def ping(resource: str) -> int:
    """Minimal connectivity/auth check -- one record, not fetch_all's full
    pagination. Health checks need to know the API is reachable, not pull
    every page of real data synchronously on every dashboard load. Returns
    the resource's total count from WooCommerce's X-WP-Total header, free --
    no extra request needed."""
    base_url = settings.BURK_ORDER_API_BASE_URL.rstrip("/")
    auth = (
        settings.BURK_ORDER_API_CONSUMER_KEY,
        settings.BURK_ORDER_API_CONSUMER_SECRET,
    )
    response = requests.get(
        f"{base_url}/wp-json/wc/v3/{resource}",
        auth=auth,
        params={"per_page": 1},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return int(response.headers.get("X-WP-Total", 0))


def fetch_all(resource: str, **extra_params) -> list[dict]:
    """GET every page of a WooCommerce v3 resource (e.g. "orders", "products")."""
    base_url = settings.BURK_ORDER_API_BASE_URL.rstrip("/")
    auth = (
        settings.BURK_ORDER_API_CONSUMER_KEY,
        settings.BURK_ORDER_API_CONSUMER_SECRET,
    )
    records: list[dict] = []
    page = 1
    while True:
        response = requests.get(
            f"{base_url}/wp-json/wc/v3/{resource}",
            auth=auth,
            params={"per_page": PAGE_SIZE, "page": page, **extra_params},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        records.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return records
