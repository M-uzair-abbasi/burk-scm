from decimal import Decimal

from django.db import models


class Channel(models.TextChoices):
    BURK = "burk", "Burk.pk"
    DARAZ = "daraz", "Daraz.pk"


class SalesOrder(models.Model):
    """A customer order pulled from a sales channel into the unified queue.

    Deliberately named SalesOrder, not Order: purchasing.PurchaseOrder is the
    supply-side order. This is the customer-facing side the Module 1 code
    reserved the `Order` name for.

    The queue's integrity guarantee — KPI #3, no dropped or duplicated records —
    rests on the (channel, external_id) unique constraint below. Ingestion is an
    idempotent upsert on that key, so re-fetching the same order updates it
    rather than ever creating a second row.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    class PaymentMode(models.TextChoices):
        PREPAID = "prepaid", "Prepaid"
        COD = "cod", "Cash on delivery"

    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    # The channel's own order identifier. Unique only *within* a channel — the
    # same string can legitimately appear on both Burk and Daraz — so the
    # uniqueness guarantee is the (channel, external_id) pair, not this alone.
    external_id = models.CharField(max_length=64)
    # Internal unified-queue number, e.g. SO-00001. Derived from the pk after
    # insert (services._assign_reference) so two concurrent ingests can never
    # collide on a blank "" under the unique index.
    reference = models.CharField(max_length=32, unique=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    source_status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=32, blank=True)
    customer_email = models.EmailField(blank=True)
    shipping_address = models.TextField(blank=True)
    shipping_address_line1 = models.CharField(max_length=255, blank=True)
    shipping_address_line2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_province = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=32, blank=True)
    shipping_country = models.CharField(max_length=2, default="PK")
    customer_instructions = models.TextField(blank=True)

    parcel_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=3, default=Decimal("0.000")
    )
    parcel_length_cm = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    parcel_width_cm = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    parcel_height_cm = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    cod_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    payment_mode = models.CharField(
        max_length=16,
        choices=PaymentMode.choices,
        default=PaymentMode.PREPAID,
    )
    shipping_service_type = models.CharField(
        max_length=64, default="standard"
    )
    pickup_account = models.CharField(max_length=64, blank=True)

    currency = models.CharField(max_length=8, default="PKR")
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    shipping_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    item_count = models.PositiveIntegerField(default=0)

    # When the customer placed it on the channel (from the payload), distinct
    # from ingested_at (when we first pulled it into the queue).
    placed_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The original source record, kept verbatim for audit and to prove the queue
    # can be reconstructed from exactly what each channel sent.
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-placed_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "external_id"],
                name="uniq_channel_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["channel", "status"]),
            models.Index(fields=["-placed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'SO draft'} ({self.get_channel_display()} {self.external_id})"


class SalesOrderLine(models.Model):
    order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    sku = models.CharField(max_length=64, blank=True)
    # Soft link: a marketplace order can reference a SKU we don't stock, so this
    # is nullable and resolved by SKU at ingest. SET_NULL keeps the order line's
    # history intact if the product is later removed.
    product = models.ForeignKey(
        "inventory.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_order_lines",
    )
    product_name = models.CharField(max_length=255, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="sales_order_line_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku or self.product_name} ×{self.quantity}"


class SyncRun(models.Model):
    """Append-only reconciliation ledger: one row per channel per sync.

    The proof artifact for KPI #3. The enforced invariant

        fetched == created + updated + duplicates_skipped + failed

    shows nothing fetched was dropped; the SalesOrder unique constraint shows
    nothing was duplicated. Never updated or deleted — like StockMovement, a
    correction is a new row, so the sync history stays reconstructible. The row
    is written once, at the end of a run, with every count already tallied.
    """

    channel = models.CharField(max_length=16, choices=Channel.choices, db_index=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    fetched = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    duplicates_skipped = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    ok = models.BooleanField(default=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [models.Index(fields=["channel", "-started_at"])]

    def __str__(self) -> str:
        return (
            f"{self.get_channel_display()} sync "
            f"(+{self.created}/~{self.updated}, {self.fetched} fetched)"
        )

    @property
    def reconciled(self) -> bool:
        """The no-dropped-records invariant: every fetched record is accounted for."""
        return (
            self.fetched
            == self.created + self.updated + self.duplicates_skipped + self.failed
        )

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "SyncRun is append-only; record a new run instead of editing one."
            )
        return super().save(*args, **kwargs)
