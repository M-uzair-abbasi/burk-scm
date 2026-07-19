from decimal import Decimal

from django.conf import settings
from django.db import models


class PurchaseOrder(models.Model):
    """A supply order placed with a supplier.

    Deliberately not named `Order`: Module 2 introduces customer orders from
    Burk.pk and Daraz.pk, and that name is reserved for them.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARTIALLY_RECEIVED = "partially_received", "Partially received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    po_number = models.CharField(max_length=32, unique=True, blank=True)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.po_number or f"PO draft #{self.pk}"

    @property
    def total_amount(self) -> Decimal:
        return sum((line.line_total for line in self.lines.all()), Decimal("0.00"))

    @property
    def is_open(self) -> bool:
        return self.status in {
            self.Status.DRAFT,
            self.Status.SUBMITTED,
            self.Status.PARTIALLY_RECEIVED,
        }


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="po_lines",
    )
    quantity_ordered = models.PositiveIntegerField()
    # A snapshot copied from the supplier tier at draft time, not a reference
    # to it. Tiers get renegotiated; pointing at one would retroactively
    # rewrite the value of orders already placed.
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity_received = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["purchase_order", "product"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "product"],
                name="uniq_product_per_po",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_ordered__gt=0),
                name="po_line_qty_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_received__lte=models.F("quantity_ordered")),
                name="po_line_received_lte_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} ×{self.quantity_ordered}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity_ordered

    @property
    def quantity_outstanding(self) -> int:
        return self.quantity_ordered - self.quantity_received
