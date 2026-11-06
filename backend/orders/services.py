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


def _safe_external_id(raw) -> str:
    if not isinstance(raw, dict):
        return ""
    for key in ("external_id", "order_id", "order_ref", "order_number", "id"):
        value = raw.get(key)
        if isinstance(value, (str, int)):
            return str(value)[:64]
    return ""


def _normalize_raw_records(connector, raw_records: list[dict]) -> tuple[list, list]:
    records = []
    errors = []
    for index, raw in enumerate(raw_records):
        try:
            records.append(connector.normalize(raw))
        except Exception as exc:  # noqa: BLE001 - account for this record and continue
            errors.append(
                {
                    "record_index": index,
                    "external_id": _safe_external_id(raw),
                    "error": str(exc),
                }
            )
    return records, errors


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
    order = (
        SalesOrder.objects.select_for_update()
        .filter(channel=norm.channel, external_id=norm.external_id)
        .first()
    )
    created = order is None
    if created:
        order = SalesOrder.objects.create(
            channel=norm.channel,
            external_id=norm.external_id,
            status=norm.status,
            source_status=norm.status,
            customer_name=norm.customer_name,
            customer_phone=norm.customer_phone,
            customer_email=norm.customer_email,
            shipping_address=norm.shipping_address,
            shipping_address_line1=norm.shipping_address_line1,
            shipping_address_line2=norm.shipping_address_line2,
            shipping_city=norm.shipping_city,
            shipping_province=norm.shipping_province,
            shipping_postal_code=norm.shipping_postal_code,
            shipping_country=norm.shipping_country,
            customer_instructions=norm.customer_instructions,
            parcel_weight_kg=norm.parcel_weight_kg,
            parcel_length_cm=norm.parcel_length_cm,
            parcel_width_cm=norm.parcel_width_cm,
            parcel_height_cm=norm.parcel_height_cm,
            cod_amount=norm.cod_amount,
            payment_mode=norm.payment_mode,
            shipping_service_type=norm.shipping_service_type,
            pickup_account=norm.pickup_account,
            currency=norm.currency,
            subtotal=norm.subtotal,
            shipping_fee=norm.shipping_fee,
            total=norm.total,
            item_count=len(norm.lines),
            placed_at=norm.placed_at,
            last_synced_at=now,
            raw_payload=norm.raw_payload,
        )
        _assign_reference(order)
        packing_started = False
    else:
        packing_started = order.packing_sessions.exists()
        order.source_status = norm.status
        if not packing_started:
            order.status = norm.status
            order.item_count = len(norm.lines)
        order.customer_name = norm.customer_name
        order.customer_phone = norm.customer_phone
        order.customer_email = norm.customer_email
        order.shipping_address = norm.shipping_address
        order.shipping_address_line1 = norm.shipping_address_line1
        order.shipping_address_line2 = norm.shipping_address_line2
        order.shipping_city = norm.shipping_city
        order.shipping_province = norm.shipping_province
        order.shipping_postal_code = norm.shipping_postal_code
        order.shipping_country = norm.shipping_country
        order.customer_instructions = norm.customer_instructions
        order.parcel_weight_kg = norm.parcel_weight_kg
        order.parcel_length_cm = norm.parcel_length_cm
        order.parcel_width_cm = norm.parcel_width_cm
        order.parcel_height_cm = norm.parcel_height_cm
        order.cod_amount = norm.cod_amount
        order.payment_mode = norm.payment_mode
        order.shipping_service_type = norm.shipping_service_type
        order.pickup_account = norm.pickup_account
        order.currency = norm.currency
        order.subtotal = norm.subtotal
        order.shipping_fee = norm.shipping_fee
        order.total = norm.total
        order.placed_at = norm.placed_at
        order.last_synced_at = now
        order.raw_payload = norm.raw_payload
        update_fields = [
            "source_status",
            "customer_name",
            "customer_phone",
            "customer_email",
            "shipping_address",
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_city",
            "shipping_province",
            "shipping_postal_code",
            "shipping_country",
            "customer_instructions",
            "parcel_weight_kg",
            "parcel_length_cm",
            "parcel_width_cm",
            "parcel_height_cm",
            "cod_amount",
            "payment_mode",
            "shipping_service_type",
            "pickup_account",
            "currency",
            "subtotal",
            "shipping_fee",
            "total",
            "placed_at",
            "last_synced_at",
            "raw_payload",
            "updated_at",
        ]
        if not packing_started:
            update_fields.extend(["status", "item_count"])
        order.save(update_fields=update_fields)

    # Once packing has started, order lines are an immutable verification
    # snapshot referenced by PackScan. Source changes remain in raw_payload and
    # source_status rather than deleting audit-linked lines.
    if not packing_started:
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
    fetched_total: int | None = None,
    pre_failed: int = 0,
    pre_errors: list[dict] | None = None,
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
    normalized_count = created = updated = duplicates = 0
    failed = pre_failed
    seen: set[str] = set()
    detail: dict = {"errors": list(pre_errors or [])}

    for norm in records:
        normalized_count += 1
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
        fetched=(
            fetched_total
            if fetched_total is not None
            else normalized_count + pre_failed
        ),
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
        raw_records = connector.fetch()
    except Exception as exc:  # noqa: BLE001 - a fetch failure is a logged run
        return ingest_records(channel, [], started=started, fetch_error=exc)

    records, errors = _normalize_raw_records(connector, raw_records)

    return ingest_records(
        channel,
        records,
        started=started,
        user=user,
        fetched_total=len(raw_records),
        pre_failed=len(errors),
        pre_errors=errors,
    )


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

    def money(value) -> str:
        return format(value, "f")

    def normalized_signature(norm: NormalizedOrder) -> dict:
        return {
            "source_status": norm.status,
            "currency": norm.currency,
            "subtotal": money(norm.subtotal),
            "shipping_fee": money(norm.shipping_fee),
            "total": money(norm.total),
            "item_count": len(norm.lines),
            "shipping_address_line1": norm.shipping_address_line1,
            "shipping_address_line2": norm.shipping_address_line2,
            "shipping_city": norm.shipping_city,
            "shipping_province": norm.shipping_province,
            "shipping_postal_code": norm.shipping_postal_code,
            "shipping_country": norm.shipping_country,
            "cod_amount": money(norm.cod_amount),
            "payment_mode": norm.payment_mode,
            "lines": sorted(
                (
                    line.sku,
                    line.product_name,
                    line.quantity,
                    money(line.unit_price),
                    money(line.line_total),
                )
                for line in norm.lines
            ),
        }

    def stored_signature(order: SalesOrder) -> dict:
        return {
            "source_status": order.source_status,
            "currency": order.currency,
            "subtotal": money(order.subtotal),
            "shipping_fee": money(order.shipping_fee),
            "total": money(order.total),
            "item_count": order.item_count,
            "shipping_address_line1": order.shipping_address_line1,
            "shipping_address_line2": order.shipping_address_line2,
            "shipping_city": order.shipping_city,
            "shipping_province": order.shipping_province,
            "shipping_postal_code": order.shipping_postal_code,
            "shipping_country": order.shipping_country,
            "cod_amount": money(order.cod_amount),
            "payment_mode": order.payment_mode,
            "lines": sorted(
                (
                    line.sku,
                    line.product_name,
                    line.quantity,
                    money(line.unit_price),
                    money(line.line_total),
                )
                for line in order.lines.all()
            ),
        }

    required_channels = list(CONNECTORS)
    checked_channels = []
    channel_errors = []
    inspected_records = 0
    dropped = []
    stale = []
    mismatched = []

    for channel in required_channels:
        try:
            connector = get_connector(channel)
            raw_records = connector.fetch()
        except Exception as exc:  # noqa: BLE001 - report a broken required source
            channel_errors.append(
                {"channel": channel, "stage": "fetch", "error": str(exc)}
            )
            continue
        checked_channels.append(channel)
        records, normalization_errors = _normalize_raw_records(connector, raw_records)
        channel_errors.extend(
            {
                "channel": channel,
                "stage": "normalize",
                **error,
            }
            for error in normalization_errors
        )
        inspected_records += len(records)

        source_by_id = {}
        for record in records:
            source_by_id.setdefault(record.external_id, record)
        stored_by_id = {
            order.external_id: order
            for order in SalesOrder.objects.filter(channel=channel).prefetch_related(
                "lines"
            )
        }
        fetched_ids = set(source_by_id)
        present = set(stored_by_id)
        dropped += [
            {"channel": channel, "external_id": ext}
            for ext in sorted(fetched_ids - present)
        ]
        stale += [
            {"channel": channel, "external_id": ext}
            for ext in sorted(present - fetched_ids)
        ]
        for external_id in sorted(fetched_ids & present):
            source_values = normalized_signature(source_by_id[external_id])
            stored_values = stored_signature(stored_by_id[external_id])
            fields = [
                field
                for field in source_values
                if source_values[field] != stored_values[field]
            ]
            if fields:
                mismatched.append(
                    {
                        "channel": channel,
                        "external_id": external_id,
                        "fields": fields,
                    }
                )

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
    ok = (
        bool(required_channels)
        and len(checked_channels) == len(required_channels)
        and inspected_records > 0
        and not channel_errors
        and not dropped
        and not stale
        and not duplicated
        and not mismatched
    )
    return {
        "dropped": len(dropped),
        "stale": len(stale),
        "duplicated": len(duplicated),
        "mismatched": len(mismatched),
        "unique": unique,
        "ok": ok,
        "required_channels": required_channels,
        "channels_checked": len(checked_channels),
        "channels_checked_detail": checked_channels,
        "inspected_records": inspected_records,
        "channel_errors": channel_errors,
        "dropped_detail": dropped,
        "stale_detail": stale,
        "duplicated_detail": duplicated,
        "mismatched_detail": mismatched,
    }
