"""Packing-station business logic — barcode verification (Module 3).

Every scan is recorded to the append-only PackScan ledger, matched or not, so
KPI #1 (intercept 100% of mismatches) is auditable. Completing a pack is the
point where stock finally moves: one SALE movement per line through
inventory.services.record_movement, in a single transaction.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from inventory.models import Product, StockMovement
from inventory.services import record_movement
from orders.models import SalesOrder, SalesOrderLine

from .models import PackingSession, PackScan

PACKABLE_STATUSES = {SalesOrder.Status.PENDING, SalesOrder.Status.CONFIRMED}


def _validate_packable_lines(order: SalesOrder) -> list[SalesOrderLine]:
    """Return the order lines only when they form a valid packing checklist."""
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValidationError(f"{order.reference} must contain at least one line.")
    if any(line.quantity <= 0 for line in lines):
        raise ValidationError(f"{order.reference} contains a non-positive quantity.")
    return lines


def start_packing(order: SalesOrder, *, user=None) -> PackingSession:
    """Open (or resume) the packing session for an order."""
    existing = order.packing_sessions.filter(
        status=PackingSession.Status.IN_PROGRESS
    ).first()
    if existing:
        return existing
    if order.status not in PACKABLE_STATUSES:
        raise ValidationError(
            f"{order.reference} is {order.get_status_display()}, not awaiting packing."
        )
    _validate_packable_lines(order)
    return PackingSession.objects.create(order=order, operator=user)


def _scanned_counts(session: PackingSession) -> dict:
    """ok-scan count keyed by order-line id for this session."""
    rows = (
        session.scans.filter(result=PackScan.Result.OK, line__isnull=False)
        .values("line")
        .annotate(n=Count("id"))
    )
    return {r["line"]: r["n"] for r in rows}


def session_progress(session: PackingSession) -> dict:
    """Per-line required/scanned/complete plus an overall flag."""
    counts = _scanned_counts(session)
    order_lines = list(session.order.lines.all())
    lines = []
    all_done = bool(order_lines)
    for line in order_lines:
        scanned = counts.get(line.id, 0)
        complete = scanned >= line.quantity
        all_done = all_done and complete
        lines.append(
            {
                "line": line,
                "required": line.quantity,
                "scanned": scanned,
                "complete": complete,
            }
        )
    return {"lines": lines, "complete": all_done}


@transaction.atomic
def record_scan(session: PackingSession, barcode: str, *, user=None) -> PackScan:
    """Validate one scanned barcode against the session's order and log it.

    Always appends a PackScan (ok / overscan / mismatch) — the mismatch rows are
    the audit proof that nothing wrong was silently packed.
    """
    if session.status != PackingSession.Status.IN_PROGRESS:
        raise ValidationError("This packing session is not in progress.")

    barcode = (barcode or "").strip()
    result = PackScan.Result.MISMATCH
    matched_line = None
    product = Product.objects.filter(barcode=barcode).first() if barcode else None

    if product is not None:
        counts = _scanned_counts(session)
        order_lines = list(session.order.lines.filter(product=product).order_by("id"))
        if order_lines:
            # Fill the first line for this product that still needs units.
            needing = next(
                (l for l in order_lines if counts.get(l.id, 0) < l.quantity), None
            )
            if needing is not None:
                result = PackScan.Result.OK
                matched_line = needing
            else:
                result = PackScan.Result.OVERSCAN
                matched_line = order_lines[0]
        # else: product exists but is not on this order -> stays MISMATCH

    return PackScan.objects.create(
        session=session,
        barcode=barcode,
        line=matched_line,
        product=product,
        result=result,
        operator=user,
    )


@transaction.atomic
def confirm_line_manual(
    session: PackingSession, line: SalesOrderLine, *, user=None
) -> PackScan:
    """Manually confirm one unit of a barcodeless line."""
    if session.status != PackingSession.Status.IN_PROGRESS:
        raise ValidationError("This packing session is not in progress.")
    if line.order_id != session.order_id:
        raise ValidationError("That line does not belong to this order.")
    if line.product_id is not None and line.product.barcode:
        raise ValidationError(f"{line.product_name} has a barcode and must be scanned.")
    counts = _scanned_counts(session)
    if counts.get(line.id, 0) >= line.quantity:
        raise ValidationError(f"{line.product_name} is already fully packed.")
    return PackScan.objects.create(
        session=session,
        barcode="",
        line=line,
        product=line.product,
        result=PackScan.Result.OK,
        manual=True,
        operator=user,
    )


@transaction.atomic
def complete_packing(session: PackingSession, *, user=None) -> SalesOrder:
    """Finish packing: verify every line, decrement stock, mark the order Packed."""
    locked_session = (
        PackingSession.objects.select_for_update()
        .select_related("order")
        .get(pk=session.pk)
    )
    if locked_session.status == PackingSession.Status.COMPLETED:
        return locked_session.order
    if locked_session.status != PackingSession.Status.IN_PROGRESS:
        raise ValidationError("This packing session is not in progress.")

    order = SalesOrder.objects.select_for_update().get(pk=locked_session.order_id)
    locked_session.order = order
    _validate_packable_lines(order)
    progress = session_progress(locked_session)
    if not progress["complete"]:
        outstanding = [
            f"{p['line'].product_name} ({p['scanned']}/{p['required']})"
            for p in progress["lines"]
            if not p["complete"]
        ]
        raise ValidationError("Not all items are verified: " + ", ".join(outstanding))

    for p in progress["lines"]:
        line = p["line"]
        if line.product_id is None:
            continue  # unstocked marketplace SKU — nothing to decrement
        record_movement(
            product=line.product,
            quantity_delta=-line.quantity,
            reason=StockMovement.Reason.SALE,
            user=user,
            note=f"Packed & dispatched for {order.reference}",
        )

    order.status = SalesOrder.Status.PACKED
    order.save(update_fields=["status", "updated_at"])
    locked_session.status = PackingSession.Status.COMPLETED
    locked_session.completed_at = timezone.now()
    locked_session.save(update_fields=["status", "completed_at"])
    session.status = locked_session.status
    session.completed_at = locked_session.completed_at
    return order


@transaction.atomic
def cancel_packing(session: PackingSession) -> PackingSession:
    if session.status != PackingSession.Status.IN_PROGRESS:
        raise ValidationError("Only an in-progress session can be cancelled.")
    session.status = PackingSession.Status.CANCELLED
    session.save(update_fields=["status"])
    return session


def packing_queue():
    """Orders awaiting packing, oldest first (receipt-time priority)."""
    return (
        SalesOrder.objects.filter(status__in=PACKABLE_STATUSES)
        .prefetch_related("lines__product")
        .order_by("placed_at", "id")
    )
