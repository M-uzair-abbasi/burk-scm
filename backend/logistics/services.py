"""Module 5 (courier booking + tracking) and Module 6 (post-delivery review
reminder) business logic.

book_shipment() is the "Instant Airway Bill Booking" requirement: called right
after an order is packed (chained from PackingViewSet.complete(), after Module
4's video dispatch), it books a courier and immediately dispatches the tracking
code — no manual data entry. advance_shipment() is where a real courier webhook
would land; DELIVERED is also Module 6's trigger, scheduling the review-request
notification rather than sending it immediately (a real deployment reminds
customers hours/days later, not the instant the parcel arrives).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.services import dispatch as dispatch_notification
from orders.models import SalesOrder

from .couriers import get_carrier
from .models import Shipment, ShipmentEvent

BOOKABLE_STATUSES = {SalesOrder.Status.PACKED}
_ADVANCE_ORDER = [Shipment.Status.BOOKED, Shipment.Status.IN_TRANSIT, Shipment.Status.DELIVERED]


def _safe_dispatch(*args, **kwargs) -> None:
    """dispatch_notification(), swallowing failures.

    Registered via transaction.on_commit(), which runs its callback
    synchronously at the atomic block's exit — still inside the caller's call
    stack — so an unguarded exception here would propagate out of
    book_shipment()/advance_shipment() exactly as if it happened before
    commit. dispatch() already isolates per-channel send failures; this only
    covers the one remaining risk, the Notification row's own write.
    """
    try:
        dispatch_notification(*args, **kwargs)
    except Exception:  # noqa: BLE001 - never break the caller over a ledger write
        pass


@transaction.atomic
def book_shipment(order: SalesOrder, *, user=None) -> Shipment | None:
    """Book a courier for a just-packed order and dispatch its tracking code.

    Idempotent: an order that already has a shipment returns it unchanged rather
    than booking a second one, the same "safe to call more than once" contract
    complete_packing's downstream hooks all share. A courier-adapter failure
    (a real integration's outage, standing in for the always-succeeding
    simulated one) degrades to no shipment rather than a 500 — the pack itself
    already succeeded and must not be reported as failed because of it.
    """
    existing = getattr(order, "shipment", None)
    if existing is not None:
        return existing
    if order.status not in BOOKABLE_STATUSES:
        raise ValidationError(
            f"{order.reference} is {order.get_status_display()}, not ready to ship."
        )

    try:
        result = get_carrier().book(order)
    except Exception:  # noqa: BLE001 - see docstring
        return None

    try:
        shipment = Shipment.objects.create(
            order=order,
            courier=result.courier,
            tracking_number=result.tracking_number,
            label_url=result.label_url,
            raw_response=result.raw,
        )
    except IntegrityError:
        # Lost a race with a concurrent booking for the same order.
        order.refresh_from_db()
        return order.shipment
    ShipmentEvent.objects.create(
        shipment=shipment,
        status=Shipment.Status.BOOKED,
        source="carrier_booking",
        raw_payload=result.raw,
    )
    order.status = SalesOrder.Status.SHIPPED
    order.save(update_fields=["status", "updated_at"])

    # Deferred to after commit: a real email/WhatsApp send must never happen
    # for a shipment the transaction could still roll back.
    transaction.on_commit(
        lambda: _safe_dispatch(
            order,
            kind=Notification.Kind.SHIPMENT_TRACKING,
            reference_event_at=shipment.booked_at,
            payload={
                "courier": shipment.courier,
                "courier_display": shipment.get_courier_display(),
                "tracking_number": shipment.tracking_number,
                "label_url": shipment.label_url,
            },
        )
    )
    return shipment


@transaction.atomic
def advance_shipment(
    shipment: Shipment, status: str, *, source: str = "simulated_webhook", raw_payload=None
) -> ShipmentEvent:
    """Record a courier status update (real webhook or simulated). DELIVERED
    also flips the order and schedules the Module 6 review reminder."""
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
        shipment=shipment, status=status, source=source, raw_payload=raw_payload or {}
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
        # Deferred to after commit — same reasoning as book_shipment above.
        # (This one only ever *schedules* a send, but the ledger row itself
        # must not exist if the delivery event it's keyed to gets rolled back.)
        transaction.on_commit(
            lambda: _safe_dispatch(
                order,
                kind=Notification.Kind.REVIEW_REQUEST,
                reference_event_at=now,
                payload={"review_link": f"https://burk.pk/review/{order.reference}"},
                scheduled_for=now + timedelta(seconds=settings.REVIEW_REMINDER_DELAY_SECONDS),
            )
        )
    return event


def shipment_integrity() -> dict:
    """Every order WE packed (a completed PackingSession) has exactly one
    Shipment — proof booking is automatically triggered whenever this system
    completes the pack. Orders a channel feed reports as already shipped/
    delivered (their pre-existing history, synced in as-is) are out of scope:
    this system never packed them, so it never had a chance to book them."""
    from fulfillment.models import PackingSession

    packed_order_ids = PackingSession.objects.filter(
        status=PackingSession.Status.COMPLETED
    ).values_list("order_id", flat=True)
    missing = SalesOrder.objects.filter(id__in=packed_order_ids, shipment__isnull=True)
    return {
        "total_shipments": Shipment.objects.count(),
        "missing_shipment_orders": [o.reference for o in missing],
        "ok": not missing.exists(),
    }
