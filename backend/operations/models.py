from django.db import models
from django.utils import timezone


class WorkItem(models.Model):
    """A durable, idempotently enqueued unit of external/background work."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        RETRY = "retry", "Retry scheduled"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=48, db_index=True)
    key = models.CharField(max_length=255, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    locked_by = models.CharField(max_length=128, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["available_at", "id"]
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["kind", "status", "available_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_attempts__gt=0),
                name="workitem_max_attempts_positive",
            ),
        ]

    def __str__(self):
        return f"{self.kind}:{self.key} ({self.get_status_display()})"


class WorkerHeartbeat(models.Model):
    """Latest liveness evidence for each worker process."""

    name = models.CharField(max_length=128, unique=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_claimed = models.PositiveIntegerField(default=0)
    last_succeeded = models.PositiveIntegerField(default=0)
    last_failed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} @ {self.last_seen_at.isoformat()}"
