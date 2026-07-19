from django.conf import settings
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def low_stock(self):
        """Products at or below their safety threshold.

        Uses `<=` rather than `<`: at exactly the threshold the safety buffer
        has started being consumed, which is the moment to reorder. The
        `safety_stock__gt=0` guard keeps untracked products (0 stock, 0
        threshold) out — they satisfy `0 <= 0` and would swamp the panel.
        Products with no threshold set are reported by out_of_stock() instead.
        """
        return self.active().filter(
            safety_stock__gt=0,
            quantity_on_hand__lte=models.F("safety_stock"),
        )

    def out_of_stock(self):
        return self.active().filter(quantity_on_hand__lte=0)

    def with_stock_status(self):
        return self.annotate(
            is_low_stock=models.Case(
                models.When(
                    safety_stock__gt=0,
                    quantity_on_hand__lte=models.F("safety_stock"),
                    then=models.Value(True),
                ),
                default=models.Value(False),
                output_field=models.BooleanField(),
            )
        )


class Product(models.Model):
    class Unit(models.TextChoices):
        PIECE = "pcs", "Pieces"
        KG = "kg", "Kilograms"
        LITRE = "ltr", "Litres"
        BOX = "box", "Box"

    sku = models.CharField(max_length=64, unique=True)
    # Module 3 scans this. Included now because it is cheap while the table is
    # empty and it keeps seed data realistic.
    # Must be NULL (not "") when absent: Postgres permits many NULLs in a
    # unique index but only one empty string, so blank strings would make the
    # second barcode-less product fail to save.
    barcode = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    name = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
    )
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.PIECE)

    # Denormalised cache of the StockMovement ledger. Written only by
    # inventory.services.record_movement(), never assigned directly.
    quantity_on_hand = models.IntegerField(default=0, editable=False)

    safety_stock = models.PositiveIntegerField(default=0)
    reorder_quantity = models.PositiveIntegerField(default=0)
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["sku"]
        indexes = [
            models.Index(fields=["is_active", "quantity_on_hand"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"

    def clean(self):
        if self.barcode == "":
            self.barcode = None

    @property
    def is_low_stock(self) -> bool:
        return self.safety_stock > 0 and self.quantity_on_hand <= self.safety_stock


class StockMovement(models.Model):
    """Append-only stock ledger. The source of truth for quantity_on_hand.

    Never updated or deleted: a mistake is corrected by posting an opposing
    movement, so history stays reconstructible. KPI 3 requires proving no
    records were dropped or duplicated, which a mutable counter cannot show.
    """

    class Reason(models.TextChoices):
        INITIAL = "initial", "Opening balance"
        PURCHASE_RECEIPT = "purchase_receipt", "Purchase receipt"
        SALE = "sale", "Sale / dispatch"
        RETURN = "return", "Customer return"
        DAMAGE = "damage", "Damage / write-off"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    quantity_delta = models.IntegerField(help_text="Signed: positive in, negative out.")
    reason = models.CharField(max_length=24, choices=Reason.choices)
    purchase_order = models.ForeignKey(
        "purchasing.PurchaseOrder",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["product", "-created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_delta=0),
                name="stockmovement_delta_nonzero",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.sku} {self.quantity_delta:+d} ({self.reason})"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "StockMovement is append-only; post a correcting movement instead."
            )
        return super().save(*args, **kwargs)
