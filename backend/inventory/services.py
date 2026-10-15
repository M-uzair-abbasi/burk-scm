"""Stock mutation. Every stock change in the system goes through here.

The ledger (StockMovement) is the source of truth; Product.quantity_on_hand is
a cache of it. Both are written in one transaction so they cannot disagree,
and `recalculate_stock` can prove it.
"""

from django.core.exceptions import PermissionDenied, ValidationError
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
    if new_quantity < 0:
        if not allow_negative:
            raise ValidationError(
                f"Insufficient stock for {locked.sku}: "
                f"{locked.quantity_on_hand} on hand, requested {quantity_delta}."
            )
        if not (user and user.is_authenticated and user.is_manager):
            raise PermissionDenied(
                "Only managers may explicitly override stock below zero."
            )
        if not note.strip():
            raise ValidationError(
                "A non-blank audit note is required to override stock below zero."
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


def sync_products_from_woocommerce() -> dict:
    """Pull every WooCommerce product that carries a SKU into our catalog.

    Mirrors the live order connector's scope decision: products with no SKU
    anywhere (made-to-order custom items, e.g. the 3D-print product) are
    skipped -- there is no stable identifier for Module 3 to scan against.
    A new SKU is created with its current WooCommerce stock recorded as an
    opening-balance movement; a known SKU gets an ADJUSTMENT movement for any
    observed drift, so the ledger -- never a raw field write -- stays the
    single source of truth `recalculate_stock` can still prove against.

    Variable products (e.g. "Cap Nuts" sized M3-M10) never carry a SKU on the
    parent -- WooCommerce puts the real, distinct SKU on each *variation*
    instead, confirmed live against real order line items which reference the
    variation's SKU directly, not the parent's. So a variable product's own
    (always-empty) SKU is skipped, and its variations are synced in its place.
    """
    from common.woocommerce import fetch_all

    raw_products = fetch_all("products")
    created = updated = unchanged = skipped_no_sku = failed = 0
    errors: list[dict] = []

    def sync_one(sku: str, name: str, manage_stock: bool, stock_quantity) -> None:
        nonlocal created, updated, unchanged, failed
        # WooCommerce allows negative stock to mean "backordered/oversold" --
        # our ledger has no such concept, so the floor is 0, not a movement
        # that would push a product negative.
        woo_stock = (
            max(0, int(stock_quantity))
            if manage_stock and stock_quantity is not None
            else 0
        )
        try:
            product = Product.objects.filter(sku=sku).first()
            if product is None:
                product = Product.objects.create(
                    sku=sku, name=name, quantity_on_hand=0
                )
                if woo_stock:
                    record_movement(
                        product=product,
                        quantity_delta=woo_stock,
                        reason=StockMovement.Reason.INITIAL,
                        note="Initial WooCommerce sync.",
                    )
                created += 1
                return

            if product.name != name:
                product.name = name
                product.save(update_fields=["name", "updated_at"])

            drift = woo_stock - product.quantity_on_hand
            if drift != 0:
                record_movement(
                    product=product,
                    quantity_delta=drift,
                    reason=StockMovement.Reason.ADJUSTMENT,
                    note=(
                        f"WooCommerce resync: observed stock {woo_stock}, "
                        f"reconciling drift of {drift:+d}."
                    ),
                )
                updated += 1
            else:
                unchanged += 1
        except (ValidationError, PermissionDenied) as exc:
            failed += 1
            errors.append({"sku": sku, "error": str(exc)})

    for raw in raw_products:
        name = str(raw.get("name", "")).strip()

        if raw.get("type") == "variable":
            for variation in fetch_all(f"products/{raw['id']}/variations"):
                v_sku = str(variation.get("sku") or "").strip()
                if not v_sku:
                    skipped_no_sku += 1
                    continue
                attrs = ", ".join(
                    str(a.get("option", ""))
                    for a in variation.get("attributes", [])
                    if a.get("option")
                )
                v_name = f"{name} - {attrs}" if attrs else (name or v_sku)
                sync_one(
                    v_sku,
                    v_name,
                    bool(variation.get("manage_stock")),
                    variation.get("stock_quantity"),
                )
            continue

        sku = str(raw.get("sku") or "").strip()
        if not sku:
            skipped_no_sku += 1
            continue
        sync_one(sku, name or sku, bool(raw.get("manage_stock")), raw.get("stock_quantity"))

    return {
        "fetched": len(raw_products),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_no_sku": skipped_no_sku,
        "failed": failed,
        "errors": errors,
    }


def ledger_balance(product: Product) -> int:
    """Rebuild on-hand quantity from the ledger alone.

    The independent recomputation `recalculate_stock` checks the cache against.
    """
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    return product.movements.aggregate(
        total=Coalesce(Sum("quantity_delta"), 0),
    )["total"]
