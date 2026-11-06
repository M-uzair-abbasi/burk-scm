from decimal import Decimal

from django.db import models


class Supplier(models.Model):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    # Stored E.164, e.g. +923001234567.
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    default_lead_time_days = models.PositiveSmallIntegerField(default=7)
    payment_terms = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SupplierProduct(models.Model):
    """Which supplier can supply which product, and on what terms."""

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="supplier_products",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        related_name="supplier_products",
    )
    supplier_sku = models.CharField(max_length=64, blank=True)
    lead_time_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Overrides the supplier default when set.",
    )
    is_preferred = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product", "supplier"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "product"],
                name="uniq_supplier_product",
            ),
            # Makes "at most one preferred supplier per product" a database
            # guarantee, so the reorder flow can never be ambiguous about
            # which supplier to preselect.
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_preferred=True),
                name="uniq_preferred_supplier_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.supplier.name} → {self.product.sku}"

    @property
    def effective_lead_time_days(self) -> int:
        if self.lead_time_days is not None:
            return self.lead_time_days
        return self.supplier.default_lead_time_days

    def price_tier_for(self, quantity: int):
        """Return the highest price tier whose minimum the quantity reaches."""
        return (
            self.price_tiers.filter(min_quantity__lte=quantity)
            .order_by("-min_quantity")
            .first()
        )

    def unit_price_for(self, quantity: int) -> Decimal | None:
        """Price per unit when buying `quantity`.

        Picks the highest tier whose minimum the quantity reaches. Returns
        None when the quantity is below every tier, which the caller must
        handle rather than assuming a price exists.
        """
        tier = self.price_tier_for(quantity)
        return tier.unit_price if tier else None


class SupplierPriceTier(models.Model):
    """Wholesale break: buy at least `min_quantity`, pay `unit_price` each."""

    supplier_product = models.ForeignKey(
        SupplierProduct,
        on_delete=models.CASCADE,
        related_name="price_tiers",
    )
    min_quantity = models.PositiveIntegerField()
    # PKR. Decimal, never float — a float→decimal migration corrupts data
    # that has already been written.
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["supplier_product", "min_quantity"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier_product", "min_quantity"],
                name="uniq_tier_per_qty",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="tier_price_nonneg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.supplier_product} @{self.min_quantity}+ = {self.unit_price}"
