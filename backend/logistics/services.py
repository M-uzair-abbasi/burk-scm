"""Durable courier booking, shipment tracking, and delivery engagement."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone

from common.redaction import redact_provider_payload
from notifications.models import Notification
from notifications.reviews import get_review_link_provider
from notifications.services import dispatch as dispatch_notification
from operations.models import WorkItem
from operations.services import enqueue
from orders.models import SalesOrder

from .couriers import get_carrier
from .couriers.base import BookingRequest
from .models import Courier, CourierWebhookEvent, Shipment, ShipmentEvent

BOOKABLE_STATUSES = {SalesOrder.Status.PACKED}
BOOK_SHIPMENT_KIND = "book_shipment"
_ADVANCE_ORDER = [
    Shipment.Status.BOOKED,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.DELIVERED,
]
_COURIER_STATUS_MAP = {
    "booked": Shipment.Status.BOOKED,
    "manifested": Shipment.Status.BOOKED,
    "picked_up": Shipment.Status.IN_TRANSIT,
    "in_transit": Shipment.Status.IN_TRANSIT,
    "out_for_delivery": Shipment.Status.IN_TRANSIT,
    "delivered": Shipment.Status.DELIVERED,
}
def _existing_shipment(order: SalesOrder) -> Shipment | None:
    try:
        return order.shipment
    except ObjectDoesNotExist:
        return None


def _booking_request(order: SalesOrder) -> BookingRequest:
    request = BookingRequest(
        order_id=order.pk,
        order_reference=order.reference,
        external_order_id=order.external_id,
        recipient_name=order.customer_name.strip(),
        phone=order.customer_phone.strip(),
        address_line1=(
            order.shipping_address_line1.strip() or order.shipping_address.strip()
        ),
        address_line2=order.shipping_address_line2.strip(),
        city=order.shipping_city.strip(),
        province=order.shipping_province.strip(),
        postal_code=order.shipping_postal_code.strip(),
        country=(order.shipping_country or "PK").upper(),
        item_count=order.item_count,
        currency=order.currency,
        declared_value=Decimal(str(order.total)),
        cod_amount=Decimal(str(order.cod_amount)),
        payment_mode=order.payment_mode,
        service_type=order.shipping_service_type,
        pickup_account=order.pickup_account,
        customer_instructions=order.customer_instructions,
        weight_kg=Decimal(str(order.parcel_weight_kg)),
        length_cm=Decimal(str(order.parcel_length_cm)),
        width_cm=Decimal(str(order.parcel_width_cm)),
        height_cm=Decimal(str(order.parcel_height_cm)),
        idempotency_key=f"burk-shipment-order-{order.pk}",
    )
    missing = [
        label
        for label, value in (
            ("recipient name", request.recipient_name),
            ("phone", request.phone),
            ("address line 1", request.address_line1),
        )
        if not value
    ]
    if missing:
        raise ValidationError(
            "Carrier booking requires " + ", ".join(missing) + "."
        )
    if request.item_count <= 0:
        raise ValidationError("Carrier booking requires a positive item count.")
    if request.declared_value < 0 or request.cod_amount < 0:
        raise ValidationError("Carrier monetary values cannot be negative.")
    if request.payment_mode == SalesOrder.PaymentMode.COD and request.cod_amount <= 0:
        raise ValidationError("COD orders require a positive COD amount.")
    return request


class CourierWebhookConflict(Exception):
    pass


def _finish_webhook_event(
    event: CourierWebhookEvent,
    *,
    outcome: str,
    shipment: Shipment | None = None,
    mapped_status: str = "",
    error_code: str = "",
) -> CourierWebhookEvent:
    event.shipment = shipment
    event.mapped_status = mapped_status
    event.outcome = outcome
    event.error_code = error_code
    event.processed_at = timezone.now()
    event.save(
        update_fields=[
            "shipment",
            "mapped_status",
            "outcome",
            "error_code",
            "processed_at",
        ]
    )
    return event


@transaction.atomic
def process_courier_webhook(
    courier: str, payload: dict, *, raw_body: bytes
) -> tuple[CourierWebhookEvent, bool]:
    """Deduplicate and apply one already-authenticated provider event."""
    if courier not in Courier.values:
        raise ValidationError("Unknown courier.")
    provider_event_id = str(payload.get("event_id", "")).strip()
    tracking_number = str(payload.get("tracking_number", "")).strip()
    provider_status = str(payload.get("status", "")).strip().lower()
    if not provider_event_id or len(provider_event_id) > 128:
        raise ValidationError("A valid provider event_id is required.")

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    redacted = redact_provider_payload(payload)
    event, created = CourierWebhookEvent.objects.get_or_create(
        courier=courier,
        provider_event_id=provider_event_id,
        defaults={
            "provider_status": provider_status[:64],
            "payload_hash": payload_hash,
            "redacted_payload": redacted,
        },
    )
    if not created:
        if event.payload_hash != payload_hash:
            raise CourierWebhookConflict(
                "A provider event ID was reused with different content."
            )
        return event, True

    if not tracking_number:
        return (
            _finish_webhook_event(
                event,
                outcome=CourierWebhookEvent.Outcome.REJECTED,
                error_code="missing_tracking_number",
            ),
            False,
        )
    shipment = (
        Shipment.objects.select_for_update()
        .select_related("order")
        .filter(courier=courier, tracking_number=tracking_number)
        .first()
    )
    if shipment is None:
        return (
            _finish_webhook_event(
                event,
                outcome=CourierWebhookEvent.Outcome.REJECTED,
                error_code="unknown_tracking_number",
            ),
            False,
        )
    mapped_status = _COURIER_STATUS_MAP.get(provider_status)
    if mapped_status is None:
        return (
            _finish_webhook_event(
                event,
                outcome=CourierWebhookEvent.Outcome.REJECTED,
                shipment=shipment,
                error_code="unknown_status",
            ),
            False,
        )

    if _ADVANCE_ORDER.index(mapped_status) <= _ADVANCE_ORDER.index(shipment.status):
        return (
            _finish_webhook_event(
                event,
                outcome=CourierWebhookEvent.Outcome.IGNORED,
                shipment=shipment,
                mapped_status=mapped_status,
            ),
            False,
        )

    advance_shipment(
        shipment,
        mapped_status,
        source=f"{courier}_webhook",
        raw_payload=redacted,
    )
    return (
        _finish_webhook_event(
            event,
            outcome=CourierWebhookEvent.Outcome.PROCESSED,
            shipment=shipment,
            mapped_status=mapped_status,
        ),
        False,
    )


def enqueue_shipment_booking(order: SalesOrder) -> WorkItem:
    """Persist exactly one courier-booking job for a packed order."""
    if _existing_shipment(order) is None and order.status not in BOOKABLE_STATUSES:
        raise ValidationError(
            f"{order.reference} is {order.get_status_display()}, not ready to ship."
        )
    request = _booking_request(order)
    existing = WorkItem.objects.filter(
        key=f"{BOOK_SHIPMENT_KIND}:{order.pk}"
    ).first()
    if existing is not None:
        return existing
    return enqueue(
        BOOK_SHIPMENT_KIND,
        str(order.pk),
        {"order_id": order.pk, "booking_request": request.to_payload()},
        max_attempts=settings.SHIPMENT_BOOKING_MAX_ATTEMPTS,
    )


def _tracking_payload(shipment: Shipment) -> dict:
    return {
        "courier": shipment.courier,
        "courier_display": shipment.get_courier_display(),
        "tracking_number": shipment.tracking_number,
        "provider_booking_id": shipment.provider_booking_id,
        "label_reference": shipment.label_reference,
        "label_url": shipment.label_url,
    }


def _enqueue_tracking_notifications(shipment: Shipment) -> None:
    dispatch_notification(
        shipment.order,
        kind=Notification.Kind.SHIPMENT_TRACKING,
        reference_event_at=shipment.booked_at,
        event_key=f"shipment-booked:{shipment.pk}",
        payload=_tracking_payload(shipment),
    )


@transaction.atomic
def _persist_booking(order_id: int, result, request: BookingRequest) -> Shipment:
    order = SalesOrder.objects.select_for_update().get(pk=order_id)
    existing = _existing_shipment(order)
    if existing is not None:
        return existing
    if order.status not in BOOKABLE_STATUSES:
        raise ValidationError(
            f"{order.reference} is {order.get_status_display()}, not ready to ship."
        )

    redacted = redact_provider_payload(result.raw)
    shipment = Shipment.objects.create(
        order=order,
        courier=result.courier,
        tracking_number=result.tracking_number,
        provider_booking_id=result.provider_booking_id or None,
        request_idempotency_key=request.idempotency_key,
        label_reference=result.label_reference,
        label_url=result.label_url,
        booking_request=request.to_payload(),
        raw_response=redacted,
    )
    ShipmentEvent.objects.create(
        shipment=shipment,
        status=Shipment.Status.BOOKED,
        source="carrier_booking",
        raw_payload=redacted,
    )
    order.status = SalesOrder.Status.SHIPPED
    order.save(update_fields=["status", "updated_at"])
    return shipment


def book_shipment(
    order: SalesOrder, *, user=None, request: BookingRequest | None = None
) -> Shipment:
    """Book idempotently through the provider, then persist and enqueue tracking.

    Provider I/O intentionally occurs outside the database transaction. The
    stable idempotency key lets a real provider return the same airway bill if
    the worker retries after a timeout or a database commit failure.
    """
    existing = _existing_shipment(order)
    if existing is not None:
        _enqueue_tracking_notifications(existing)
        return existing
    if order.status not in BOOKABLE_STATUSES:
        raise ValidationError(
            f"{order.reference} is {order.get_status_display()}, not ready to ship."
        )

    request = request or _booking_request(order)
    result = get_carrier().book(request)
    shipment = _persist_booking(order.pk, result, request)
    _enqueue_tracking_notifications(shipment)
    return shipment


def process_shipment_booking_work(item) -> Shipment:
    order = SalesOrder.objects.get(pk=item.payload["order_id"])
    payload = item.payload.get("booking_request")
    request = BookingRequest.from_payload(payload) if payload else _booking_request(order)
    return book_shipment(order, request=request)


def shipment_job_detail(
    order: SalesOrder, *, include_error: bool = True
) -> dict | None:
    """Stable public projection of the courier automation's durable state."""
    item = WorkItem.objects.filter(
        key=f"{BOOK_SHIPMENT_KIND}:{order.pk}"
    ).first()
    if item is None:
        if _existing_shipment(order) is None:
            return None
        return {
            "status": WorkItem.Status.SUCCEEDED,
            "attempts": 0,
            "max_attempts": 0,
            "next_attempt_at": None,
            "error": "",
            "completed_at": None,
        }
    return {
        "status": item.status,
        "attempts": item.attempts,
        "max_attempts": item.max_attempts,
        "next_attempt_at": (
            item.available_at if item.status == WorkItem.Status.RETRY else None
        ),
        "error": item.last_error if include_error else "",
        "completed_at": item.completed_at,
    }


@transaction.atomic
def advance_shipment(
    shipment: Shipment,
    status: str,
    *,
    source: str = "simulated_webhook",
    raw_payload=None,
) -> ShipmentEvent:
    """Append a courier update; delivery atomically schedules the review job."""
    shipment = (
        Shipment.objects.select_for_update()
        .select_related("order")
        .get(pk=shipment.pk)
    )
    if shipment.status == Shipment.Status.DELIVERED:
        raise ValidationError(f"{shipment.tracking_number} is already delivered.")
    if status not in Shipment.Status.values:
        raise ValidationError(f"Unknown shipment status: {status!r}")
    if _ADVANCE_ORDER.index(status) <= _ADVANCE_ORDER.index(shipment.status):
        raise ValidationError(
            f"Cannot move {shipment.tracking_number} from "
            f"{shipment.get_status_display()} back to {Shipment.Status(status).label}."
        )

    now = timezone.now()
    event = ShipmentEvent.objects.create(
        shipment=shipment,
        status=status,
        source=source,
        raw_payload=raw_payload or {},
    )
    shipment.status = status
    update_fields = ["status"]
    if status == Shipment.Status.IN_TRANSIT:
        shipment.in_transit_at = now
        update_fields.append("in_transit_at")
    elif status == Shipment.Status.DELIVERED:
        shipment.delivered_at = now
        update_fields.append("delivered_at")
    shipment.save(update_fields=update_fields)

    if status == Shipment.Status.DELIVERED:
        order = shipment.order
        order.status = SalesOrder.Status.DELIVERED
        order.save(update_fields=["status", "updated_at"])
        dispatch_notification(
            order,
            kind=Notification.Kind.REVIEW_REQUEST,
            reference_event_at=now,
            event_key=f"shipment-delivered:{event.pk}",
            payload={
                "review_link": get_review_link_provider().build(
                    order,
                    event_key=f"shipment-delivered:{event.pk}",
                )
            },
            scheduled_for=now
            + timedelta(seconds=settings.REVIEW_REMINDER_DELAY_SECONDS),
        )
    return event


def shipment_integrity() -> dict:
    """Report every completed pack lacking a successfully persisted shipment."""
    from fulfillment.models import PackingSession

    packed_orders = SalesOrder.objects.filter(
        packing_sessions__status=PackingSession.Status.COMPLETED,
        shipment__isnull=True,
    ).distinct()
    missing = []
    pending = []
    failed = []
    for order in packed_orders:
        missing.append(order.reference)
        detail = shipment_job_detail(order)
        if detail is None:
            continue
        if detail["status"] == WorkItem.Status.FAILED:
            failed.append(order.reference)
        elif detail["status"] in {
            WorkItem.Status.PENDING,
            WorkItem.Status.PROCESSING,
            WorkItem.Status.RETRY,
        }:
            pending.append(order.reference)
    return {
        "total_shipments": Shipment.objects.count(),
        "missing_shipment_orders": missing,
        "pending_booking_orders": pending,
        "failed_booking_orders": failed,
        "ok": not missing,
    }
