from datetime import timedelta
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import WorkItem, WorkerHeartbeat
from .exceptions import PermanentWorkError
from common.correlation import correlation_id, get_correlation_id

logger = logging.getLogger("burk.worker")


def retry_delay_seconds(attempt: int) -> int:
    return min(
        settings.WORKER_BACKOFF_MAX_SECONDS,
        settings.WORKER_BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)),
    )


def get_handler(kind: str):
    from .handlers import get_handler as resolve

    return resolve(kind)


def enqueue(
    kind: str,
    business_key: str,
    payload: dict,
    *,
    available_at=None,
    max_attempts: int = 5,
) -> WorkItem:
    """Create one durable job for a business key, or return the existing job."""
    key = f"{kind}:{business_key}"
    item, created = WorkItem.objects.get_or_create(
        key=key,
        defaults={
            "kind": kind,
            "payload": payload,
            "correlation_id": (
                "" if get_correlation_id() == "-" else get_correlation_id()
            ),
            "available_at": available_at or timezone.now(),
            "max_attempts": max_attempts,
        },
    )
    if not created and (item.kind != kind or item.payload != payload):
        raise ValueError(
            f"Work key {key!r} was reused with a different kind or payload."
        )
    return item


@transaction.atomic
def claim_due(
    *, limit: int = 10, worker_name: str = "worker", now=None, kinds=None
):
    """Lease due work with PostgreSQL `skip_locked` so workers never overlap."""
    now = now or timezone.now()
    lease_until = now + timedelta(seconds=settings.WORKER_LEASE_SECONDS)

    # A crashed worker that consumed its final attempt cannot remain PROCESSING
    # forever; make the terminal state explicit before selecting candidates.
    WorkItem.objects.filter(
        status=WorkItem.Status.PROCESSING,
        lease_expires_at__lte=now,
        attempts__gte=F("max_attempts"),
    ).update(
        status=WorkItem.Status.FAILED,
        completed_at=now,
        lease_expires_at=None,
        locked_at=None,
        locked_by="",
        last_error="Worker lease expired after the final attempt.",
    )

    due = Q(
        status__in=[WorkItem.Status.PENDING, WorkItem.Status.RETRY],
        available_at__lte=now,
    ) | Q(
        status=WorkItem.Status.PROCESSING,
        lease_expires_at__lte=now,
    )
    queryset = WorkItem.objects.select_for_update(skip_locked=True).filter(
        due, attempts__lt=F("max_attempts")
    )
    if kinds:
        queryset = queryset.filter(kind__in=kinds)
    items = list(queryset.order_by("available_at", "id")[: max(0, limit)])
    for item in items:
        item.status = WorkItem.Status.PROCESSING
        item.attempts += 1
        item.locked_by = worker_name
        item.locked_at = now
        item.lease_expires_at = lease_until
        item.save(
            update_fields=[
                "status",
                "attempts",
                "locked_by",
                "locked_at",
                "lease_expires_at",
                "updated_at",
            ]
        )
    return items


@transaction.atomic
def _mark_succeeded(item: WorkItem, *, now=None):
    now = now or timezone.now()
    locked = WorkItem.objects.select_for_update().get(pk=item.pk)
    locked.status = WorkItem.Status.SUCCEEDED
    locked.completed_at = now
    locked.last_error = ""
    locked.locked_by = ""
    locked.locked_at = None
    locked.lease_expires_at = None
    locked.save(
        update_fields=[
            "status",
            "completed_at",
            "last_error",
            "locked_by",
            "locked_at",
            "lease_expires_at",
            "updated_at",
        ]
    )


@transaction.atomic
def _mark_failed(item: WorkItem, exc: Exception, *, now=None):
    now = now or timezone.now()
    locked = WorkItem.objects.select_for_update().get(pk=item.pk)
    terminal = (
        isinstance(exc, PermanentWorkError)
        or locked.attempts >= locked.max_attempts
    )
    locked.status = WorkItem.Status.FAILED if terminal else WorkItem.Status.RETRY
    locked.last_error = f"{exc.__class__.__name__}: {exc}"
    locked.locked_by = ""
    locked.locked_at = None
    locked.lease_expires_at = None
    if terminal:
        locked.completed_at = now
    else:
        backoff = retry_delay_seconds(locked.attempts)
        locked.available_at = now + timedelta(seconds=backoff)
    locked.save(
        update_fields=[
            "status",
            "last_error",
            "locked_by",
            "locked_at",
            "lease_expires_at",
            "completed_at",
            "available_at",
            "updated_at",
        ]
    )


def process_due(
    *, limit: int = 10, worker_name: str = "worker", now=None, kinds=None
):
    """Claim and execute bounded work, recording retries and heartbeat.

    Lease each item immediately before its handler starts. Pre-leasing an entire
    batch lets a slow first handler consume the lease window of later rows before
    they execute, making those rows reclaimable by another worker prematurely.
    """
    claimed = []
    succeeded = failed = 0
    for _ in range(max(0, limit)):
        next_item = claim_due(
            limit=1,
            worker_name=worker_name,
            now=now,
            kinds=kinds,
        )
        if not next_item:
            break
        item = next_item[0]
        claimed.append(item)
        context_token = correlation_id.set(
            item.correlation_id or f"work-{item.pk}"
        )
        logger.info(
            "work_item_started",
            extra={
                "event": "work_item_started",
                "work_item_id": item.pk,
                "status": item.status,
                "attempt": item.attempts,
            },
        )
        try:
            get_handler(item.kind)(item)
        except Exception as exc:  # noqa: BLE001 - durable retry boundary
            _mark_failed(item, exc)
            failed += 1
            item.refresh_from_db()
            logger.warning(
                "work_item_failed",
                extra={
                    "event": "work_item_failed",
                    "work_item_id": item.pk,
                    "status": item.status,
                    "attempt": item.attempts,
                },
            )
        else:
            _mark_succeeded(item)
            succeeded += 1
            logger.info(
                "work_item_succeeded",
                extra={
                    "event": "work_item_succeeded",
                    "work_item_id": item.pk,
                    "status": WorkItem.Status.SUCCEEDED,
                    "attempt": item.attempts,
                },
            )
        finally:
            correlation_id.reset(context_token)

    WorkerHeartbeat.objects.update_or_create(
        name=worker_name,
        defaults={
            "last_seen_at": timezone.now(),
            "last_claimed": len(claimed),
            "last_succeeded": succeeded,
            "last_failed": failed,
        },
    )
    return claimed
