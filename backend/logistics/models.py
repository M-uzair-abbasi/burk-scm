"""Module 5 — Logistics Integration & Automated Tracking.

One Shipment per order, booked instantly once packing (and Module 4's dispatch)
finishes. ShipmentEvent is the append-only log of every status change — booked,
in transit, delivered — the same ledger-plus-cache shape as StockMovement/
Product.quantity_on_hand: Shipment.status is a denormalised cache of the latest
event, kept in sync by advance_shipment(). A real courier's delivery webhook
would create these events directly; simulate_delivery_update stands in for that
webhook in this environment (mirrors simulate_new_order for order feeds).
"""

from __future__ import annotations

from django.db import models


class Courier(models.TextChoices):
    LEOPARD = "leopard", "Leopard Courier"
    TCS = "tcs", "TCS"
    TRAX = "trax", "Trax"
    MNP = "mnp", "M&P"


class Shipment(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        IN_TRANSIT = "in_transit", "In transit"
        DELIVERED = "delivered", "Delivered"

    order = models.OneToOneField(
        "orders.SalesOrder",
        on_delete=models.CASCADE,
        related_name="shipment",
    )
    courier = models.CharField(max_length=16, choices=Courier.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.BOOKED,
        db_index=True,
    )
    tracking_number = models.CharField(max_length=32, unique=True)
    label_url = models.CharField(max_length=255, blank=True)
    # The courier API's own booking response, kept verbatim — the same audit
    # role raw_payload plays for orders.
    raw_response = models.JSONField(default=dict, blank=True)

    booked_at = models.DateTimeField(auto_now_add=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-booked_at", "-id"]

    def __str__(self) -> str:
        return f"{self.tracking_number} ({self.get_courier_display()}, {self.get_status_display()})"


class ShipmentEvent(models.Model):
    """Append-only status-change log — one row per courier webhook (real or
    simulated). Never edited: a correction is a new event, like StockMovement."""

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="events",
    )
    status = models.CharField(max_length=16, choices=Shipment.Status.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)
    # "simulated_webhook" here; a real integration would record the courier's
    # own webhook source/signature instead.
    source = models.CharField(max_length=32, default="simulated_webhook")
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self) -> str:
        return f"{self.shipment_id} -> {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "ShipmentEvent is append-only; record a new event instead of editing one."
            )
        return super().save(*args, **kwargs)
