"""Durable notification outbox shared by packaging, shipment, and reviews."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from common.redaction import redact_provider_payload
from operations.exceptions import PermanentWorkError
from operations.services import enqueue, process_due, retry_delay_seconds

from .channels import get_channel
from .models import Notification, NotificationDeliveryEvent

SEND_NOTIFICATION_KIND = "send_notification"
DEFAULT_CHANNELS = (Notification.Channel.EMAIL, Notification.Channel.WHATSAPP)
DELIVERED_PROVIDER_STATUSES = frozenset({"delivered", "read"})
FAILED_PROVIDER_STATUSES = frozenset({"failed", "undelivered", "rejected"})

_RECIPIENT_FIELD = {
    Notification.Channel.EMAIL: "customer_email",
    Notification.Channel.WHATSAPP: "customer_phone",
}


def _business_key(order, kind, channel, event_key) -> str:
    material = f"{order.pk}|{kind}|{channel}|{event_key}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return f"notification:{digest}"


@transaction.atomic
def dispatch(
    order,
    *,
    kind: str,
    reference_event_at,
    payload: dict,
    channels=DEFAULT_CHANNELS,
    scheduled_for=None,
    event_key: str | None = None,
    max_attempts: int = 5,
) -> list[Notification]:
    """Persist one idempotent outbox row/job per channel; never send inline."""
    event_key = event_key or reference_event_at.isoformat()
    available_at = scheduled_for or timezone.now()
    rows = []
    for channel in channels:
        recipient = getattr(order, _RECIPIENT_FIELD[channel], "") or ""
        idempotency_key = _business_key(order, kind, channel, event_key)
        notification, created = Notification.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "order": order,
                "kind": kind,
                "channel": channel,
                "recipient": recipient,
                "reference_event_at": reference_event_at,
                "scheduled_for": scheduled_for,
                "next_attempt_at": available_at,
                "payload": payload,
            },
        )
        if not created and (
            notification.order_id != order.pk
            or notification.kind != kind
            or notification.channel != channel
            or notification.payload != payload
        ):
            raise ValueError(
                f"Notification event key {idempotency_key!r} was reused "
                "with different immutable content."
            )
        enqueue(
            SEND_NOTIFICATION_KIND,
            str(notification.pk),
            {"notification_id": notification.pk},
            available_at=available_at,
            max_attempts=max_attempts,
        )
        rows.append(notification)
    return rows


def _record_failure(notification, item, exc, *, terminal: bool):
    now = timezone.now()
    notification.attempt_count = item.attempts
    notification.error = str(exc)
    notification.terminal_error_class = exc.__class__.__name__ if terminal else ""
    notification.status = (
        Notification.Status.FAILED if terminal else Notification.Status.RETRYING
    )
    notification.next_attempt_at = (
        None
        if terminal
        else now + timedelta(seconds=retry_delay_seconds(item.attempts))
    )
    notification.save(
        update_fields=[
            "attempt_count",
            "error",
            "terminal_error_class",
            "status",
            "next_attempt_at",
        ]
    )


class NotificationWebhookConflict(Exception):
    pass


class ProviderContractError(ValueError):
    pass


def _finish_delivery_event(
    event: NotificationDeliveryEvent,
    *,
    outcome: str,
    notification: Notification | None = None,
    error_code: str = "",
) -> NotificationDeliveryEvent:
    event.notification = notification
    event.outcome = outcome
    event.error_code = error_code
    event.processed_at = timezone.now()
    event.save(
        update_fields=[
            "notification",
            "outcome",
            "error_code",
            "processed_at",
        ]
    )
    return event


@transaction.atomic
def process_delivery_receipt(
    channel: str, payload: dict, *, raw_body: bytes
) -> tuple[NotificationDeliveryEvent, bool]:
    """Deduplicate and apply one already-authenticated provider receipt."""
    if channel not in Notification.Channel.values:
        raise ValidationError("Unknown notification channel.")
    provider_event_id = str(payload.get("event_id", "")).strip()
    provider_message_id = str(payload.get("provider_message_id", "")).strip()
    provider_status = str(payload.get("status", "")).strip().lower()
    if not provider_event_id or len(provider_event_id) > 128:
        raise ValidationError("A valid provider event_id is required.")

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    event, created = NotificationDeliveryEvent.objects.get_or_create(
        channel=channel,
        provider_event_id=provider_event_id,
        defaults={
            "provider_message_id": provider_message_id[:255],
            "provider_status": provider_status[:64],
            "payload_hash": payload_hash,
            "redacted_payload": redact_provider_payload(payload),
        },
    )
    if not created:
        if event.payload_hash != payload_hash:
            raise NotificationWebhookConflict(
                "A provider event ID was reused with different content."
            )
        return event, True

    if not provider_message_id or len(provider_message_id) > 255:
        return (
            _finish_delivery_event(
                event,
                outcome=NotificationDeliveryEvent.Outcome.REJECTED,
                error_code=(
                    "missing_provider_message_id"
                    if not provider_message_id
                    else "invalid_provider_message_id"
                ),
            ),
            False,
        )

    notification = (
        Notification.objects.select_for_update()
        .select_related("order")
        .filter(channel=channel, provider_message_id=provider_message_id)
        .first()
    )
    if notification is None:
        return (
            _finish_delivery_event(
                event,
                outcome=NotificationDeliveryEvent.Outcome.REJECTED,
                error_code="unknown_provider_message_id",
            ),
            False,
        )

    if notification.status == Notification.Status.SENT and notification.acknowledged_at:
        return (
            _finish_delivery_event(
                event,
                outcome=NotificationDeliveryEvent.Outcome.IGNORED,
                notification=notification,
            ),
            False,
        )

    if provider_status in FAILED_PROVIDER_STATUSES:
        notification.status = Notification.Status.FAILED
        notification.error = f"Provider reported {provider_status}."
        notification.terminal_error_class = "ProviderDeliveryFailure"
        notification.next_attempt_at = None
        notification.save(
            update_fields=[
                "status",
                "error",
                "terminal_error_class",
                "next_attempt_at",
            ]
        )
        return (
            _finish_delivery_event(
                event,
                outcome=NotificationDeliveryEvent.Outcome.FAILED,
                notification=notification,
            ),
            False,
        )

    if provider_status not in DELIVERED_PROVIDER_STATUSES:
        return (
            _finish_delivery_event(
                event,
                outcome=NotificationDeliveryEvent.Outcome.REJECTED,
                notification=notification,
                error_code="unknown_status",
            ),
            False,
        )

    notification.status = Notification.Status.SENT
    notification.acknowledged_at = timezone.now()
    notification.error = ""
    notification.terminal_error_class = ""
    notification.next_attempt_at = None
    notification.save(
        update_fields=[
            "status",
            "acknowledged_at",
            "error",
            "terminal_error_class",
            "next_attempt_at",
        ]
    )
    return (
        _finish_delivery_event(
            event,
            outcome=NotificationDeliveryEvent.Outcome.DELIVERED,
            notification=notification,
        ),
        False,
    )


def process_notification_work(item):
    """Worker handler for one Notification outbox row."""
    notification = Notification.objects.select_related("order").get(
        pk=item.payload["notification_id"]
    )
    if notification.status in {
        Notification.Status.SENT,
        Notification.Status.ACCEPTED,
    }:
        return notification

    notification.status = Notification.Status.PROCESSING
    notification.attempt_count = item.attempts
    notification.next_attempt_at = None
    notification.save(
        update_fields=["status", "attempt_count", "next_attempt_at"]
    )

    if not notification.recipient:
        field = _RECIPIENT_FIELD[notification.channel]
        exc = ValueError(f"Order has no {field} on file.")
        _record_failure(notification, item, exc, terminal=True)
        raise PermanentWorkError(str(exc))

    try:
        detail = get_channel(notification.channel).send(notification)
    except Exception as exc:
        terminal = item.attempts >= item.max_attempts
        _record_failure(notification, item, exc, terminal=terminal)
        raise

    if detail is None:
        detail = {}
    if not isinstance(detail, dict):
        exc = ProviderContractError("Provider send result must be an object.")
        _record_failure(notification, item, exc, terminal=True)
        raise PermanentWorkError(str(exc))

    now = timezone.now()
    acknowledged = detail.get("acknowledged", True)
    if not isinstance(acknowledged, bool):
        exc = ProviderContractError(
            "Provider acknowledged result must be a boolean."
        )
        _record_failure(notification, item, exc, terminal=True)
        raise PermanentWorkError(str(exc))
    provider_message_id = str(detail.get("provider_message_id", "")).strip()
    if len(provider_message_id) > 255:
        exc = ProviderContractError("Provider message ID exceeds 255 characters.")
        _record_failure(notification, item, exc, terminal=True)
        raise PermanentWorkError(str(exc))
    if not acknowledged and not provider_message_id:
        exc = ProviderContractError(
            "An unacknowledged provider acceptance requires a provider message ID."
        )
        _record_failure(notification, item, exc, terminal=True)
        raise PermanentWorkError(str(exc))
    notification.status = (
        Notification.Status.SENT
        if acknowledged
        else Notification.Status.ACCEPTED
    )
    notification.sent_at = now
    notification.acknowledged_at = now if acknowledged else None
    notification.attempt_count = item.attempts
    notification.provider_message_id = provider_message_id
    notification.payload = {
        **notification.payload,
        **redact_provider_payload(detail),
    }
    notification.error = ""
    notification.terminal_error_class = ""
    notification.next_attempt_at = None
    notification.save(
        update_fields=[
            "status",
            "sent_at",
            "acknowledged_at",
            "attempt_count",
            "provider_message_id",
            "payload",
            "error",
            "terminal_error_class",
            "next_attempt_at",
        ]
    )
    return notification


def dispatch_due_scheduled(*, now=None, limit: int = 100) -> list[Notification]:
    """Compatibility scheduler tick: drain only due notification jobs."""
    claimed = process_due(
        limit=limit,
        worker_name="notification-scheduler",
        now=now,
        kinds=[SEND_NOTIFICATION_KIND],
    )
    ids = [item.payload["notification_id"] for item in claimed]
    by_id = Notification.objects.in_bulk(ids)
    return [by_id[pk] for pk in ids if pk in by_id]


def latency_report(kind: str | None = None, *, threshold_seconds: int = 180) -> dict:
    """Strict send-acknowledgement and required-channel evidence report."""
    qs = Notification.objects.select_related("order")
    if kind:
        qs = qs.filter(kind=kind)

    now = timezone.now()
    sent = list(
        qs.filter(
            status=Notification.Status.SENT,
            acknowledged_at__isnull=False,
        )
    )
    unacknowledged = list(
        qs.filter(status=Notification.Status.ACCEPTED)
    ) + list(
        qs.filter(
            status=Notification.Status.SENT,
            acknowledged_at__isnull=True,
        )
    )
    breaches = [n for n in sent if (n.latency_seconds or 0) > threshold_seconds]
    failed_rows = list(qs.filter(status=Notification.Status.FAILED))

    active_statuses = [
        Notification.Status.SCHEDULED,
        Notification.Status.PROCESSING,
        Notification.Status.RETRYING,
    ]
    if kind == Notification.Kind.PACKAGING_VIDEO:
        stuck = list(qs.filter(status__in=active_statuses)) + unacknowledged
    else:
        stuck = list(
            qs.filter(
                status=Notification.Status.SCHEDULED,
                scheduled_for__lte=now,
            )
        ) + list(
            qs.filter(
                status__in=[
                    Notification.Status.PROCESSING,
                    Notification.Status.RETRYING,
                ]
            )
        ) + unacknowledged

    required_missing = []
    if kind == Notification.Kind.PACKAGING_VIDEO:
        required = set(settings.NOTIFICATION_REQUIRED_CHANNELS)
        events: dict[tuple, set] = {}
        for row in qs:
            events.setdefault(
                (row.order_id, row.reference_event_at), set()
            ).add(row.channel)
        for (order_id, reference), present in events.items():
            missing = sorted(required - present)
            if missing:
                required_missing.append(
                    {
                        "order_id": order_id,
                        "reference_event_at": reference,
                        "channels": missing,
                    }
                )

    duplicate_groups = list(
        qs.values("order_id", "kind", "channel", "reference_event_at")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    evidence_count = len(sent)
    evidence_required = kind == Notification.Kind.PACKAGING_VIDEO
    return {
        "kind": kind,
        "sent": evidence_count,
        "evidence_count": evidence_count,
        "failed": len(failed_rows),
        "stuck": len(stuck),
        "pending": len(stuck),
        "missing_required_channels": required_missing,
        "duplicates": duplicate_groups,
        "max_latency_seconds": (
            max(n.latency_seconds for n in sent) if sent else None
        ),
        "breaches": breaches,
        "stuck_detail": stuck,
        "failed_detail": failed_rows,
        "ok": (
            (not evidence_required or evidence_count > 0)
            and not breaches
            and not stuck
            and not failed_rows
            and not required_missing
            and not duplicate_groups
        ),
    }
