"""Module 4 — Automated Video Surveillance & Customer Transparency.

One PackagingRecording per PackingSession: capture starts with packing, sealing
copies PackingSession.completed_at, and a durable worker materializes and
compresses the clip. The timestamps and checksums retain an independent audit
trail for KPI #2 and media integrity.
"""

from __future__ import annotations

from django.db import models


class PackagingRecording(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RECORDING = "recording", "Recording"
        QUEUED = "queued", "Queued for processing"
        PROCESSING = "processing", "Processing"
        RETRYING = "retrying", "Retrying"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    session = models.OneToOneField(
        "fulfillment.PackingSession",
        on_delete=models.CASCADE,
        related_name="recording",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    # Paths are relative to MEDIA_ROOT, not absolute — portable across environments.
    raw_path = models.CharField(max_length=255, blank=True)
    compressed_path = models.CharField(max_length=255, blank=True)
    camera_name = models.CharField(max_length=64, blank=True)
    capture_handle = models.JSONField(default=dict, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    raw_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    compressed_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    raw_checksum = models.CharField(max_length=64, blank=True)
    compressed_checksum = models.CharField(max_length=64, blank=True)
    customer_link_token = models.CharField(max_length=512, blank=True)
    customer_link_issued_at = models.DateTimeField(null=True, blank=True)
    raw_deleted_at = models.DateTimeField(null=True, blank=True)
    compressed_deleted_at = models.DateTimeField(null=True, blank=True)

    # The order-sealed timestamp this recording responds to — KPI #2's clock start.
    sealed_at = models.DateTimeField(null=True, blank=True)
    capture_started_at = models.DateTimeField(null=True, blank=True)
    capture_stopped_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    compressed_at = models.DateTimeField(null=True, blank=True)
    processing_attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.TextField(blank=True)
    terminal_error_class = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Recording for pack {self.session_id} ({self.get_status_display()})"
