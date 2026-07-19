"""Purchase-order business logic.

Kept out of the views so the PO-number generation, submit transition and
receive-into-stock flow are transactional and unit-testable. Every stock
change a receipt causes still goes through inventory.services.record_movement,
so the ledger stays the single source of truth.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from inventory.models import StockMovement
from inventory.services import record_movement
from suppliers.models import SupplierProduct

from .models import PurchaseOrder, PurchaseOrderLine


def _assign_po_number(po: PurchaseOrder) -> None:
    """Derive the human PO number from the guaranteed-unique pk.

    Done after the insert so two concurrent drafts can never collide on a
    blank "" po_number under the unique index.
    """
    po.po_number = f"PO-{po.pk:05d}"
    po.save(update_fields=["po_number"])


def _preferred_supplier_product(product, supplier=None):
    qs = SupplierProduct.objects.filter(
        product=product, is_active=True
    ).select_related("supplier")
    if supplier is not None:
        return qs.filter(supplier=supplier).first()
    # is_preferred is a DB-guaranteed at-most-one; fall back to any link.
    return qs.filter(is_preferred=True).first() or qs.first()


@transaction.atomic
def create_po(*, supplier, user=None, expected_date=None, notes="", lines=None):
    """Create a DRAFT purchase order with optional lines.

    `lines` is an iterable of dicts: {product, quantity_ordered, unit_price}.
    """
    po = PurchaseOrder.objects.create(
        supplier=supplier,
        created_by=user,
        expected_date=expected_date,
        notes=notes,
        status=PurchaseOrder.Status.DRAFT,
    )
    _assign_po_number(po)
    for line in lines or []:
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            product=line["product"],
            quantity_ordered=line["quantity_ordered"],
            unit_price=line["unit_price"],
        )
    return po


@transaction.atomic
def create_reorder_po(*, product, user=None, quantity=None, supplier=None):
    """Draft a PO to replenish one product from its preferred supplier.

    Preselects the preferred supplier, orders reorder_quantity (overridable),
    and snapshots the tier unit price. Degrades to a clear error rather than a
    500 when the product has no supplier, no reorder quantity, or no price
    tier covering the quantity.
    """
    sp = _preferred_supplier_product(product, supplier)
    if sp is None:
        raise ValidationError(
            f"No supplier is linked to {product.sku}; cannot reorder from the dashboard."
        )

    quantity = quantity or product.reorder_quantity
    if not quantity or quantity <= 0:
        raise ValidationError(
            f"{product.sku} has no reorder quantity set; specify one to reorder."
        )

    unit_price = sp.unit_price_for(quantity)
    if unit_price is None:
        raise ValidationError(
            f"No price tier covers {quantity} units for {product.sku}."
        )

    return create_po(
        supplier=sp.supplier,
        user=user,
        lines=[
            {
                "product": product,
                "quantity_ordered": quantity,
                "unit_price": unit_price,
            }
        ],
    )


@transaction.atomic
def submit_po(po: PurchaseOrder) -> PurchaseOrder:
    """DRAFT -> SUBMITTED, stamping expected_date = today + supplier lead time."""
    if po.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError(
            f"Only draft POs can be submitted; {po.po_number} is {po.get_status_display()}."
        )
    if not po.lines.exists():
        raise ValidationError("Cannot submit a PO with no lines.")

    lead = po.supplier.default_lead_time_days
    po.status = PurchaseOrder.Status.SUBMITTED
    po.submitted_at = timezone.now()
    po.expected_date = timezone.localdate() + timedelta(days=lead)
    po.save(update_fields=["status", "submitted_at", "expected_date", "updated_at"])
    return po


@transaction.atomic
def receive_po(po: PurchaseOrder, *, receipts=None, user=None) -> PurchaseOrder:
    """Receive stock against a PO, posting a PURCHASE_RECEIPT per line.

    `receipts` is an optional list of {"line": id, "quantity": n}. When omitted,
    every line's full outstanding quantity is received. Sets the PO to RECEIVED
    when nothing remains outstanding, otherwise PARTIALLY_RECEIVED.
    """
    if po.status not in {
        PurchaseOrder.Status.SUBMITTED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    }:
        raise ValidationError(
            f"{po.po_number} is not in a receivable state ({po.get_status_display()})."
        )

    requested = None
    if receipts:
        requested = {int(item["line"]): int(item["quantity"]) for item in receipts}

    any_received = False
    for line in po.lines.select_related("product"):
        outstanding = line.quantity_outstanding
        if outstanding <= 0:
            continue
        qty = outstanding if requested is None else requested.get(line.id, 0)
        if qty <= 0:
            continue
        if qty > outstanding:
            raise ValidationError(
                f"Cannot receive {qty} of {line.product.sku}; "
                f"only {outstanding} outstanding."
            )
        record_movement(
            product=line.product,
            quantity_delta=qty,
            reason=StockMovement.Reason.PURCHASE_RECEIPT,
            user=user,
            purchase_order=po,
            note=f"Receipt against {po.po_number}",
        )
        line.quantity_received += qty
        line.save(update_fields=["quantity_received"])
        any_received = True

    if not any_received:
        raise ValidationError("Nothing to receive: quantities were zero or already received.")

    # Re-query from the base manager: po.lines may carry a stale prefetch
    # cache from when the PO was loaded (before this receipt updated the rows),
    # which would misreport a fully received PO as only partially received.
    fresh_lines = PurchaseOrderLine.objects.filter(purchase_order=po)
    fully_received = all(line.quantity_outstanding == 0 for line in fresh_lines)
    po.status = (
        PurchaseOrder.Status.RECEIVED
        if fully_received
        else PurchaseOrder.Status.PARTIALLY_RECEIVED
    )
    if fully_received:
        po.received_at = timezone.now()
    po.save(update_fields=["status", "received_at", "updated_at"])
    return po
