"""Module 4 — Automated Video Surveillance & Customer Transparency.

One PackagingRecording per PackingSession: the overhead-camera capture of that
order's packing sequence, then its compressed hand-off copy. `sealed_at` copies
PackingSession.completed_at — the fixed point KPI #2 latency is measured from,
kept here too so a recording's own audit trail doesn't depend on a live join.
"""

from __future__ import annotations

from django.db import models


class PackagingRecording(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RECORDING = "recording", "Recording"
        PROCESSING = "processing", "Processing"
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
    duration_seconds = models.FloatField(null=True, blank=True)
    raw_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    compressed_size_bytes = models.PositiveIntegerField(null=True, blank=True)

    # The order-sealed timestamp this recording responds to — KPI #2's clock start.
    sealed_at = models.DateTimeField()
    captured_at = models.DateTimeField(null=True, blank=True)
    compressed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Recording for pack {self.session_id} ({self.get_status_display()})"
