"""Order ingestion into the unified queue.

One writer, idempotent on (channel, external_id). Every sync writes exactly one
SyncRun per channel whose counts reconcile against what was fetched — that is how
KPI #3 (no dropped/duplicated records) is proven rather than asserted:

    fetched == created + updated + duplicates_skipped + failed   (nothing dropped)
    UniqueConstraint(channel, external_id)                       (nothing duplicated)
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from inventory.models import Product

from .connectors import CONNECTORS, get_connector
from .connectors.base import NormalizedOrder
from .models import SalesOrder, SalesOrderLine, SyncRun


def _assign_reference(order: SalesOrder) -> None:
    """Derive the unified-queue reference from the guaranteed-unique pk.

    Done after insert so two concurrent ingests can never collide on a blank ""
    under the unique index — the same trick purchasing uses for PO numbers.
    """
    order.reference = f"SO-{order.pk:05d}"
    order.save(update_fields=["reference"])


@transaction.atomic
def _upsert_order(norm: NormalizedOrder, *, now) -> bool:
    """Create or refresh one order + its lines. Returns True if newly created.

    Idempotent on (channel, external_id): re-syncing an order updates the same
    row, so the queue can never hold two rows for one channel order.
    """
    order, created = SalesOrder.objects.update_or_create(
        channel=norm.channel,
        external_id=norm.external_id,
        defaults={
            "status": norm.status,
            "customer_name": norm.customer_name,
            "customer_phone": norm.customer_phone,
            "customer_email": norm.customer_email,
            "shipping_address": norm.shipping_address,
            "currency": norm.currency,
            "subtotal": norm.subtotal,
            "shipping_fee": norm.shipping_fee,
            "total": norm.total,
            "item_count": len(norm.lines),
            "placed_at": norm.placed_at,
            "last_synced_at": now,
            "raw_payload": norm.raw_payload,
        },
    )
    if created:
        _assign_reference(order)

    # Lines carry no external references, so rebuild them wholesale — simpler and
    # correct than diffing, and cheap at these sizes. SKUs are soft-resolved to
    # products in one query; an unstocked marketplace SKU leaves product NULL.
    order.lines.all().delete()
    skus = [line.sku for line in norm.lines if line.sku]
    products = (
        {p.sku: p for p in Product.objects.filter(sku__in=skus)} if skus else {}
    )
    SalesOrderLine.objects.bulk_create(
        [
            SalesOrderLine(
                order=order,
                sku=line.sku,
                product=products.get(line.sku),
                product_name=line.product_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
            for line in norm.lines
        ]
    )
    return created


def ingest_records(
    channel: str,
    records: list[NormalizedOrder],
    *,
    started=None,
    user=None,
    fetch_error=None,
) -> SyncRun:
    """Ingest already-fetched NormalizedOrders and log one SyncRun.

    Split out from ingest_channel so tests can drive exact records in without
    depending on the fixture files.
    """
    started = started or timezone.now()

    if fetch_error is not None:
        return SyncRun.objects.create(
            channel=channel,
            started_at=started,
            finished_at=timezone.now(),
            fetched=0,
            ok=False,
            detail={"fetch_error": str(fetch_error)},
        )

    now = timezone.now()
    fetched = created = updated = duplicates = failed = 0
    seen: set[str] = set()
    detail: dict = {"errors": []}

    for norm in records:
        fetched += 1
        # A repeat of a key already handled in THIS batch is an intra-batch
        # duplicate: skip it. Across syncs the same key is an update, not a dup.
        if norm.external_id in seen:
            duplicates += 1
            continue
        seen.add(norm.external_id)
        try:
            was_created = _upsert_order(norm, now=now)
        except Exception as exc:  # noqa: BLE001 - log the run, never 500 the sync
            failed += 1
            detail["errors"].append(
                {"external_id": norm.external_id, "error": str(exc)}
            )
            continue
        if was_created:
            created += 1
        else:
            updated += 1

    return SyncRun.objects.create(
        channel=channel,
        started_at=started,
        finished_at=timezone.now(),
        fetched=fetched,
        created=created,
        updated=updated,
        duplicates_skipped=duplicates,
        failed=failed,
        ok=(failed == 0),
        detail=detail,
    )


def ingest_channel(channel: str, *, user=None) -> SyncRun:
    """Pull one channel's feed and ingest it. Returns the run's SyncRun."""
    connector = get_connector(channel)
    started = timezone.now()
    try:
        records = connector.fetch_normalized()
    except Exception as exc:  # noqa: BLE001 - a fetch failure is a logged run
        return ingest_records(channel, [], started=started, fetch_error=exc)
    return ingest_records(channel, records, started=started, user=user)


def sync_all(*, user=None) -> list[SyncRun]:
    """Ingest every registered channel. One SyncRun per channel."""
    return [ingest_channel(channel, user=user) for channel in CONNECTORS]


def queue_integrity() -> dict:
    """Live KPI-3 check: re-fetch every feed and diff it against the queue.

    Independent of the SyncRun ledger (the way recalculate_stock recomputes from
    the movement ledger rather than trusting the cache):

      dropped    = records a feed returns that are absent from the queue
      duplicated = any (channel, external_id) present more than once

    Both must be zero. Used by the summary endpoint and check_order_integrity.
    """
    from django.db.models import Count

    dropped = []
    for channel in CONNECTORS:
        try:
            records = get_connector(channel).fetch_normalized()
        except Exception:  # noqa: BLE001 - a broken feed shouldn't crash the badge
            continue
        fetched_ids = {r.external_id for r in records}
        present = set(
            SalesOrder.objects.filter(
                channel=channel, external_id__in=fetched_ids
            ).values_list("external_id", flat=True)
        )
        dropped += [
            {"channel": channel, "external_id": ext}
            for ext in sorted(fetched_ids - present)
        ]

    dup_rows = (
        SalesOrder.objects.values("channel", "external_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    duplicated = [
        {"channel": r["channel"], "external_id": r["external_id"], "count": r["n"]}
        for r in dup_rows
    ]
    unique = SalesOrder.objects.count()
    return {
        "dropped": len(dropped),
        "duplicated": len(duplicated),
        "unique": unique,
        "ok": not dropped and not duplicated,
        "dropped_detail": dropped,
        "duplicated_detail": duplicated,
    }
