"""Customer-notification ledger — shared dispatch mechanism for Modules 4, 5 and 6.

One row per (order, kind, channel) dispatch attempt: the packaging video (Module
4), the shipment tracking code (Module 5), and the post-delivery review reminder
(Module 6) all write here rather than each module inventing its own send-log.
`reference_event_at` is the timestamp KPI #2 (Synchronous Communication Latency)
measures against — session.completed_at for a packaging video, shipment.booked_at
for tracking. `scheduled_for` lets a notification be created now but sent later
(the review reminder), without a task queue: a management command sweeps for due
rows, the same "manual trigger stands in for a cron" pattern sync_orders uses.
"""

from __future__ import annotations

from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        PACKAGING_VIDEO = "packaging_video", "Packaging video"
        SHIPMENT_TRACKING = "shipment_tracking", "Shipment tracking"
        REVIEW_REQUEST = "review_request", "Review request"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(
        "orders.SalesOrder",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    # Email address or phone number resolved from the order at dispatch time, kept
    # here (not looked up again) so history is correct even if the order changes.
    recipient = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )
    # The order-lifecycle event this notification responds to — the KPI #2 clock start.
    reference_event_at = models.DateTimeField()
    # Null = send immediately at dispatch(). Set = held for dispatch_due_scheduled().
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    # Channel-specific content: video_url/duration, tracking_number/courier,
    # review_link — whatever the caller attached when dispatching.
    payload = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["order", "kind"]),
            models.Index(fields=["status", "scheduled_for"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} -> {self.get_channel_display()} ({self.get_status_display()})"

    @property
    def latency_seconds(self) -> float | None:
        """Elapsed time between the triggering event and actual send — the KPI #2 number."""
        if not self.sent_at:
            return None
        return (self.sent_at - self.reference_event_at).total_seconds()
