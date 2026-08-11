"""Dispatch pipeline for the shared Notification ledger.

dispatch() is the single writer: every Module 4/5/6 send goes through it, so the
KPI #2 latency proof (sent_at - reference_event_at) and the failure-isolation
behaviour (a bad send never raises into the caller's transaction — inventory,
packing and shipment booking must never fail because a WhatsApp send failed) live
in one place. scheduled_for support means the same function serves both an
instant dispatch (Module 4/5) and a delayed one (Module 6's review reminder)
without a task queue: dispatch_due_scheduled() is the manual "cron tick", run by
a management command the same way sync_orders stands in for a real scheduler.
"""

from __future__ import annotations

from django.utils import timezone

from .channels import get_channel
from .models import Notification

DEFAULT_CHANNELS = (Notification.Channel.EMAIL, Notification.Channel.WHATSAPP)

_RECIPIENT_FIELD = {
    Notification.Channel.EMAIL: "customer_email",
    Notification.Channel.WHATSAPP: "customer_phone",
}


def _send(notification: Notification) -> Notification:
    """Attempt one send and record the outcome. Never raises."""
    try:
        channel = get_channel(notification.channel)
        detail = channel.send(notification)
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        if detail:
            notification.payload = {**notification.payload, **detail}
        notification.save(update_fields=["status", "sent_at", "payload"])
    except Exception as exc:  # noqa: BLE001 - log the failure, never break the caller
        notification.status = Notification.Status.FAILED
        notification.error = str(exc)
        notification.save(update_fields=["status", "error"])
    return notification


def dispatch(
    order,
    *,
    kind: str,
    reference_event_at,
    payload: dict,
    channels=DEFAULT_CHANNELS,
    scheduled_for=None,
) -> list[Notification]:
    """Create one Notification per channel and send it now unless scheduled_for
    is in the future. Always returns the created rows, sent or not — a missing
    recipient or a channel error lands as status=FAILED, not an exception."""
    now = timezone.now()
    created = []
    for channel in channels:
        notification = Notification.objects.create(
            order=order,
            kind=kind,
            channel=channel,
            recipient=getattr(order, _RECIPIENT_FIELD[channel], "") or "",
            reference_event_at=reference_event_at,
            scheduled_for=scheduled_for,
            payload=payload,
        )
        if scheduled_for is None or scheduled_for <= now:
            _send(notification)
        created.append(notification)
    return created


def dispatch_due_scheduled(*, now=None) -> list[Notification]:
    """Send every SCHEDULED notification whose time has come. The cron-proxy
    sweep for Module 6's review reminder (and anything else scheduled later)."""
    now = now or timezone.now()
    due = Notification.objects.filter(
        status=Notification.Status.SCHEDULED, scheduled_for__lte=now
    )
    return [_send(n) for n in due]


def latency_report(kind: str | None = None, *, threshold_seconds: int = 180) -> dict:
    """KPI #2 proof: every sent notification of `kind` initiated within
    threshold_seconds of its reference event, and nothing stuck un-sent."""
    qs = Notification.objects.all()
    if kind:
        qs = qs.filter(kind=kind)

    sent = list(qs.filter(status=Notification.Status.SENT))
    breaches = [n for n in sent if (n.latency_seconds or 0) > threshold_seconds]
    # "Stuck" = still SCHEDULED past its own due time — dispatch() always sends
    # a None/past scheduled_for immediately, so the only way a row stays
    # SCHEDULED is a real future scheduled_for; once that time has passed
    # without dispatch_due_scheduled() picking it up, it's missed, not merely
    # waiting. (Filtering scheduled_for__isnull=True here would never match
    # anything, since that case is sent inline and never reaches SCHEDULED.)
    stuck = list(
        qs.filter(status=Notification.Status.SCHEDULED, scheduled_for__lte=timezone.now())
    )
    failed = qs.filter(status=Notification.Status.FAILED).count()

    latencies = [n.latency_seconds for n in sent if n.latency_seconds is not None]
    return {
        "kind": kind,
        "sent": len(sent),
        "failed": failed,
        "stuck": len(stuck),
        "max_latency_seconds": max(latencies) if latencies else None,
        "breaches": breaches,
        "stuck_detail": stuck,
        "ok": not breaches and not stuck,
    }
