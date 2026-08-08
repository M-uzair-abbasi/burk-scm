from django.conf import settings
from django.db import models


class PackingSession(models.Model):
    """One packing attempt for a customer order — the Module 3 workflow.

    An order is picked from the Module 2 queue, its items are scanned against the
    packing list, and on completion stock is decremented (SALE movements) and the
    order becomes Packed. At most one in-progress session per order (the partial
    unique constraint below).
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        "orders.SalesOrder",
        on_delete=models.PROTECT,
        related_name="packing_sessions",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        db_index=True,
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="packing_sessions",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            # A single order can only be actively packed once at a time. Partial
            # so completed/cancelled sessions don't block a re-pack.
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status="in_progress"),
                name="one_active_packing_session_per_order",
            ),
        ]

    def __str__(self) -> str:
        return f"Pack {self.order_id} ({self.get_status_display()})"


class PackScan(models.Model):
    """Append-only log of every barcode scanned at the packing station.

    Every scan is recorded — matched, mismatched, or overscanned — because KPI #1
    (intercept 100% of mismatches) is proven precisely by the fact that no
    mismatch is ever missing from this ledger nor ever counted as packing
    progress. Never edited: a correction is a new scan, like StockMovement and
    SyncRun.
    """

    class Result(models.TextChoices):
        OK = "ok", "Matched"
        MISMATCH = "mismatch", "Mismatch — wrong item"
        OVERSCAN = "overscan", "Overscan — quantity already met"

    session = models.ForeignKey(
        PackingSession,
        on_delete=models.CASCADE,
        related_name="scans",
    )
    barcode = models.CharField(max_length=64, blank=True)
    # Nullable + SET_NULL: a mismatch has no line/product, and history survives if
    # a product is later removed.
    line = models.ForeignKey(
        "orders.SalesOrderLine",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pack_scans",
    )
    product = models.ForeignKey(
        "inventory.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pack_scans",
    )
    result = models.CharField(max_length=16, choices=Result.choices, db_index=True)
    # True when an operator manually confirms a line whose product has no barcode.
    manual = models.BooleanField(default=False)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="pack_scans",
    )
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scanned_at", "-id"]
        indexes = [models.Index(fields=["session", "-scanned_at"])]

    def __str__(self) -> str:
        return f"{self.barcode or '(manual)'} -> {self.get_result_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "PackScan is append-only; record a new scan instead of editing one."
            )
        return super().save(*args, **kwargs)
