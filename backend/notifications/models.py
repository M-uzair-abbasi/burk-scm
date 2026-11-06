"""Customer-notification ledger — shared dispatch mechanism for Modules 4, 5 and 6.

One row per (order, kind, channel) dispatch attempt: the packaging video (Module
4), the shipment tracking code (Module 5), and the post-delivery review reminder
(Module 6) all write here rather than each module inventing its own send-log.
`reference_event_at` is the timestamp KPI #2 (Synchronous Communication Latency)
measures against — session.completed_at for a packaging video, shipment.booked_at
for tracking. `scheduled_for` lets a notification be created now but made
eligible later (the review reminder). Every row has a durable WorkItem whose
`available_at` controls when the continuously running worker may claim it.
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
        PROCESSING = "processing", "Processing"
        RETRYING = "retrying", "Retrying"
        ACCEPTED = "accepted", "Provider accepted"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(
        "orders.SalesOrder",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    idempotency_key = models.CharField(max_length=96, unique=True)
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
    # Null means the durable job is immediately due. A timestamp defers worker
    # eligibility until that time; dispatch() itself never performs network I/O.
    scheduled_for = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    provider_message_id = models.CharField(max_length=255, blank=True)
    terminal_error_class = models.CharField(max_length=128, blank=True)
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
            models.Index(
                fields=["status", "next_attempt_at"],
                name="notification_retry_due_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "provider_message_id"],
                condition=~models.Q(provider_message_id=""),
                name="uniq_notification_provider_message",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} -> {self.get_channel_display()} ({self.get_status_display()})"

    @property
    def latency_seconds(self) -> float | None:
        """Elapsed time to persisted delivery acknowledgement (KPI #2)."""
        if not self.acknowledged_at:
            return None
        return (self.acknowledged_at - self.reference_event_at).total_seconds()


class NotificationDeliveryEvent(models.Model):
    """Replay ledger for a signed provider delivery receipt."""

    class Outcome(models.TextChoices):
        RECEIVED = "received", "Received"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        IGNORED = "ignored", "Ignored"
        REJECTED = "rejected", "Rejected"

    channel = models.CharField(max_length=16, choices=Notification.Channel.choices)
    provider_event_id = models.CharField(max_length=128)
    provider_message_id = models.CharField(max_length=255)
    notification = models.ForeignKey(
        Notification,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_events",
    )
    provider_status = models.CharField(max_length=64, blank=True)
    payload_hash = models.CharField(max_length=64)
    redacted_payload = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(
        max_length=16,
        choices=Outcome.choices,
        default=Outcome.RECEIVED,
    )
    error_code = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "provider_event_id"],
                name="uniq_notification_provider_event",
            )
        ]
        indexes = [
            models.Index(fields=["channel", "outcome", "-received_at"])
        ]

    def __str__(self):
        return f"{self.channel}:{self.provider_event_id} ({self.outcome})"
