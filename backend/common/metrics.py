"""Bounded operational aggregates for Manager dashboards and alerting."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Max, Min, Q
from django.utils import timezone

from fulfillment.models import PackScan
from notifications.models import Notification
from operations.models import WorkItem
from orders.models import Channel, SyncRun
from surveillance.models import PackagingRecording


def _seconds(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        value = value.total_seconds()
    return round(max(0.0, float(value)), 2)


def _thresholds() -> dict[str, int]:
    return {
        "queue_depth": settings.METRICS_MAX_QUEUE_DEPTH,
        "oldest_due_seconds": settings.METRICS_MAX_OLDEST_DUE_SECONDS,
        "retrying_work": settings.METRICS_MAX_RETRYING_WORK,
        "failed_work": settings.METRICS_MAX_FAILED_WORK,
        "source_lag_seconds": settings.METRICS_MAX_SOURCE_LAG_SECONDS,
        "source_failures": settings.METRICS_MAX_SOURCE_FAILURES,
        "notification_latency_seconds": settings.METRICS_MAX_NOTIFICATION_LATENCY_SECONDS,
        "notification_failures": settings.METRICS_MAX_NOTIFICATION_FAILURES,
        "shipment_booking_failures": settings.METRICS_MAX_SHIPMENT_BOOKING_FAILURES,
        "media_processing_seconds": settings.METRICS_MAX_MEDIA_PROCESSING_SECONDS,
        "media_failures": settings.METRICS_MAX_MEDIA_FAILURES,
    }


def _breach(breaches, code: str, value, threshold) -> None:
    if value is not None and value > threshold:
        breaches.append({"code": code, "value": value, "threshold": threshold})


def operational_metrics(*, now=None) -> dict:
    """Return fixed-cardinality aggregates in five database queries.

    No raw event rows, payloads, recipients, file paths, or credentials are
    returned. The only grouped dimension is the fixed two-value Channel enum.
    """
    now = now or timezone.now()
    window_start = now - timedelta(hours=settings.METRICS_WINDOW_HOURS)
    thresholds = _thresholds()

    active_work = Q(
        status__in=[
            WorkItem.Status.PENDING,
            WorkItem.Status.PROCESSING,
            WorkItem.Status.RETRY,
        ]
    )
    due_work = Q(
        status__in=[WorkItem.Status.PENDING, WorkItem.Status.RETRY],
        available_at__lte=now,
    ) | Q(
        status=WorkItem.Status.PROCESSING,
        lease_expires_at__lte=now,
    )
    work = WorkItem.objects.aggregate(
        active=Count("id", filter=active_work),
        due=Count("id", filter=due_work),
        retrying=Count("id", filter=Q(status=WorkItem.Status.RETRY)),
        failed=Count("id", filter=Q(status=WorkItem.Status.FAILED)),
        processing=Count("id", filter=Q(status=WorkItem.Status.PROCESSING)),
        oldest_due_at=Min("available_at", filter=due_work),
        shipment_booking_failures=Count(
            "id",
            filter=Q(kind="book_shipment", status=WorkItem.Status.FAILED),
        ),
    )
    oldest_due_age = (
        _seconds(now - work["oldest_due_at"]) if work["oldest_due_at"] else 0.0
    )

    source_rows = {
        row["channel"]: row
        for row in SyncRun.objects.values("channel").annotate(
            last_finished_at=Max("finished_at"),
            failed_runs=Count(
                "id",
                filter=Q(ok=False, started_at__gte=window_start),
            ),
        )
    }
    source_details = []
    missing_sources = []
    source_lags = []
    source_failures = 0
    for channel in Channel.values:
        row = source_rows.get(channel, {})
        last_finished_at = row.get("last_finished_at")
        lag = _seconds(now - last_finished_at) if last_finished_at else None
        failed_runs = row.get("failed_runs", 0)
        if last_finished_at is None:
            missing_sources.append(channel)
        else:
            source_lags.append(lag)
        source_failures += failed_runs
        source_details.append(
            {
                "channel": channel,
                "last_finished_at": last_finished_at,
                "lag_seconds": lag,
                "failed_runs": failed_runs,
            }
        )

    scans = PackScan.objects.filter(scanned_at__gte=window_start).aggregate(
        total=Count("id"),
        mismatches=Count("id", filter=Q(result=PackScan.Result.MISMATCH)),
        overscans=Count("id", filter=Q(result=PackScan.Result.OVERSCAN)),
    )

    acknowledgement_latency = ExpressionWrapper(
        F("acknowledged_at") - F("reference_event_at"),
        output_field=DurationField(),
    )
    notification = Notification.objects.filter(
        created_at__gte=window_start
    ).aggregate(
        total=Count("id"),
        acknowledged=Count("id", filter=Q(acknowledged_at__isnull=False)),
        awaiting_acknowledgement=Count(
            "id", filter=Q(status=Notification.Status.ACCEPTED)
        ),
        failed=Count("id", filter=Q(status=Notification.Status.FAILED)),
        average_latency=Avg(
            acknowledgement_latency,
            filter=Q(acknowledged_at__isnull=False),
        ),
        max_latency=Max(
            acknowledgement_latency,
            filter=Q(acknowledged_at__isnull=False),
        ),
    )

    media_processing_duration = ExpressionWrapper(
        F("compressed_at") - F("capture_stopped_at"),
        output_field=DurationField(),
    )
    media = PackagingRecording.objects.filter(created_at__gte=window_start).aggregate(
        total=Count("id"),
        processed=Count("id", filter=Q(status=PackagingRecording.Status.READY)),
        failed=Count("id", filter=Q(status=PackagingRecording.Status.FAILED)),
        average_processing=Avg(
            media_processing_duration,
            filter=Q(
                compressed_at__isnull=False,
                capture_stopped_at__isnull=False,
            ),
        ),
        max_processing=Max(
            media_processing_duration,
            filter=Q(
                compressed_at__isnull=False,
                capture_stopped_at__isnull=False,
            ),
        ),
    )

    queue = {
        "active": work["active"],
        "due": work["due"],
        "retrying": work["retrying"],
        "failed": work["failed"],
        "processing": work["processing"],
        "oldest_due_age_seconds": oldest_due_age,
    }
    sources = {
        "channels": source_details,
        "missing": missing_sources,
        "max_lag_seconds": max(source_lags, default=None),
        "failed_runs": source_failures,
    }
    packing = {
        "scans": scans["total"],
        "mismatches_intercepted": scans["mismatches"],
        "overscans_intercepted": scans["overscans"],
    }
    notifications = {
        "total": notification["total"],
        "acknowledged": notification["acknowledged"],
        "awaiting_acknowledgement": notification["awaiting_acknowledgement"],
        "failed": notification["failed"],
        "average_latency_seconds": _seconds(notification["average_latency"]),
        "max_latency_seconds": _seconds(notification["max_latency"]),
    }
    shipments = {"booking_failures": work["shipment_booking_failures"]}
    media_summary = {
        "total": media["total"],
        "processed": media["processed"],
        "failed": media["failed"],
        "average_processing_seconds": _seconds(media["average_processing"]),
        "max_processing_seconds": _seconds(media["max_processing"]),
    }

    breaches = [
        {
            "code": f"sources.{channel}.missing",
            "value": None,
            "threshold": "latest successful or failed sync required",
        }
        for channel in missing_sources
    ]
    _breach(breaches, "queue.active", queue["active"], thresholds["queue_depth"])
    _breach(
        breaches,
        "queue.oldest_due_age_seconds",
        queue["oldest_due_age_seconds"],
        thresholds["oldest_due_seconds"],
    )
    _breach(
        breaches, "queue.retrying", queue["retrying"], thresholds["retrying_work"]
    )
    _breach(breaches, "queue.failed", queue["failed"], thresholds["failed_work"])
    _breach(
        breaches,
        "sources.max_lag_seconds",
        sources["max_lag_seconds"],
        thresholds["source_lag_seconds"],
    )
    _breach(
        breaches,
        "sources.failed_runs",
        sources["failed_runs"],
        thresholds["source_failures"],
    )
    _breach(
        breaches,
        "notifications.max_latency_seconds",
        notifications["max_latency_seconds"],
        thresholds["notification_latency_seconds"],
    )
    _breach(
        breaches,
        "notifications.failed",
        notifications["failed"],
        thresholds["notification_failures"],
    )
    _breach(
        breaches,
        "shipments.booking_failures",
        shipments["booking_failures"],
        thresholds["shipment_booking_failures"],
    )
    _breach(
        breaches,
        "media.max_processing_seconds",
        media_summary["max_processing_seconds"],
        thresholds["media_processing_seconds"],
    )
    _breach(
        breaches,
        "media.failed",
        media_summary["failed"],
        thresholds["media_failures"],
    )

    return {
        "ok": not breaches,
        "checked_at": now,
        "window": {
            "hours": settings.METRICS_WINDOW_HOURS,
            "starts_at": window_start,
        },
        "queue": queue,
        "sources": sources,
        "packing": packing,
        "notifications": notifications,
        "shipments": shipments,
        "media": media_summary,
        "thresholds": thresholds,
        "breaches": breaches,
    }
