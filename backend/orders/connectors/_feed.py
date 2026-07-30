"""Shared helpers for the simulated connectors.

The base feed for each channel is a JSON fixture in data/. A connector also
merges an optional data/<channel>_injected.json, which the `simulate_new_order`
command appends to — that is how a live demo makes the queue grow by exactly one
order on the next sync. The injected file is absent until the command writes it.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_json(path: Path) -> list:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def load_feed(channel: str) -> list[dict]:
    base = load_json(DATA_DIR / f"{channel}_orders.json")
    injected = load_json(DATA_DIR / f"{channel}_injected.json")
    return list(base) + list(injected)
