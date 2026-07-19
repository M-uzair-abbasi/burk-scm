"""Stock mutation. Every stock change in the system goes through here.

The ledger (StockMovement) is the source of truth; Product.quantity_on_hand is
a cache of it. Both are written in one transaction so they cannot disagree,
and `recalculate_stock` can prove it.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Product, StockMovement


@transaction.atomic
def record_movement(
    *,
    product: Product,
    quantity_delta: int,
    reason: str,
    user=None,
    purchase_order=None,
    note: str = "",
    allow_negative: bool = False,
) -> StockMovement:
    """Append a movement to the ledger and update the cached quantity.

    Args:
        product: Product to adjust.
        quantity_delta: Signed change. Positive is inbound, negative outbound.
        reason: A StockMovement.Reason value.
        user: Who did it. Kept for the audit trail.
        purchase_order: Set when the movement is a PO receipt.
        note: Free text, shown in the ledger view.
        allow_negative: Permit the result to go below zero. Needed when a
            manager corrects an overstated count downward past zero; refused
            by default so ordinary outbound movements cannot oversell.

    Returns:
        The created StockMovement.

    Raises:
        ValidationError: delta is zero, or the result would go negative and
            allow_negative is False.
    """
    if quantity_delta == 0:
        raise ValidationError("quantity_delta must be non-zero.")

    # Lock the row for the rest of the transaction. Without this, two
    # concurrent movements both read the same starting value and the second
    # write silently discards the first. select_for_update() requires an open
    # transaction, which the decorator guarantees.
    locked = Product.objects.select_for_update().get(pk=product.pk)

    new_quantity = locked.quantity_on_hand + quantity_delta
    if new_quantity < 0 and not allow_negative:
        raise ValidationError(
            f"Insufficient stock for {locked.sku}: "
            f"{locked.quantity_on_hand} on hand, requested {quantity_delta}."
        )

    movement = StockMovement.objects.create(
        product=locked,
        quantity_delta=quantity_delta,
        reason=reason,
        purchase_order=purchase_order,
        created_by=user,
        note=note,
    )

    locked.quantity_on_hand = new_quantity
    locked.save(update_fields=["quantity_on_hand", "updated_at"])

    # Keep the caller's instance usable rather than silently stale.
    product.quantity_on_hand = new_quantity

    return movement


def ledger_balance(product: Product) -> int:
    """Rebuild on-hand quantity from the ledger alone.

    The independent recomputation `recalculate_stock` checks the cache against.
    """
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    return product.movements.aggregate(
        total=Coalesce(Sum("quantity_delta"), 0),
    )["total"]
