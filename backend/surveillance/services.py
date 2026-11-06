"""Packing-camera lifecycle and durable recording processing."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.services import dispatch as dispatch_notification
from operations.exceptions import PermanentWorkError
from operations.services import enqueue, retry_delay_seconds

from .camera import CaptureHandle, get_camera
from .ffmpeg import detect_container, run_ffmpeg
from .models import PackagingRecording
from .signing import customer_video_token, customer_video_url

PROCESS_RECORDING_KIND = "process_packaging_recording"
RAW_DIR = "packaging_videos/raw"
COMPRESSED_DIR = "packaging_videos/compressed"
COMPRESSED_SCALE = "160:120"
COMPRESSED_CRF = "32"


def _media_path(relative: str) -> str:
    full = os.path.join(settings.MEDIA_ROOT, relative)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


def _compress(raw_abs_path: str, compressed_abs_path: str) -> None:
    run_ffmpeg(
        [
            "-protocol_whitelist",
            "file",
            "-f",
            detect_container(raw_abs_path),
            "-i",
            raw_abs_path,
            "-vf",
            f"scale={COMPRESSED_SCALE}",
            "-c:v",
            "libx264",
            "-crf",
            COMPRESSED_CRF,
            "-preset",
            "ultrafast",
            "-an",
            compressed_abs_path,
        ]
    )


def _checksum(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_uploaded_recording(session, uploaded_file) -> PackagingRecording:
    """Land a browser-recorded clip at the raw_path start_recording() reserved.

    Only the browser camera backend calls this -- the simulated and hardware
    adapters materialize their own raw file inside process_recording_work via
    camera.stop()/recover() instead. Writes to a temp file in the same
    directory and renames into place so a worker racing this upload never
    observes a partially-written file.
    """
    recording = getattr(session, "recording", None)
    if recording is None:
        raise ValidationError("Recording has not been started for this session.")
    if recording.sealed_at is not None:
        raise ValidationError(
            "This pack has already been sealed; the recording can no longer "
            "be replaced."
        )
    if uploaded_file.size > settings.PACKAGING_UPLOAD_MAX_BYTES:
        raise ValidationError(
            f"Recording is too large ({uploaded_file.size} bytes, limit is "
            f"{settings.PACKAGING_UPLOAD_MAX_BYTES})."
        )
    # Reject anything that isn't actually a WebM/MP4 container before it ever
    # touches disk or ffmpeg/ffprobe -- an uploaded file is untrusted input,
    # and letting ffmpeg auto-detect the format from content (rather than
    # pinning it, as detect_container()/_compress() now do) is the standard
    # way a crafted non-video file turns into an SSRF/local-file-read.
    header = uploaded_file.read(12)
    uploaded_file.seek(0)
    if not (header.startswith(b"\x1a\x45\xdf\xa3") or header[4:8] == b"ftyp"):
        raise ValidationError("Recording must be a WebM or MP4 clip.")

    final_path = _media_path(recording.raw_path)
    tmp_path = f"{final_path}.part-{uuid.uuid4().hex}"
    with open(tmp_path, "wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
    os.replace(tmp_path, final_path)
    return recording


def _capture_handle(recording: PackagingRecording) -> CaptureHandle | None:
    if not recording.capture_handle:
        return None
    return CaptureHandle(
        token=recording.capture_handle.get("token", ""),
        metadata=recording.capture_handle.get("metadata", {}),
    )


def start_recording(session, *, user=None) -> PackagingRecording:
    """Begin an idempotent camera capture when the operator starts packing.

    Camera startup failure is recorded but never blocks packing. The worker can
    later call the adapter's recovery path after the session is sealed.
    """
    existing = getattr(session, "recording", None)
    if existing is not None:
        return existing

    token = uuid.uuid4().hex
    recording, created = PackagingRecording.objects.get_or_create(
        session=session,
        defaults={
            "raw_path": f"{RAW_DIR}/{session.id}-{token}.mp4",
            "compressed_path": f"{COMPRESSED_DIR}/{session.id}-{token}.mp4",
        },
    )
    if not created:
        return recording

    try:
        camera = get_camera()
        health = camera.health()
        if not health.get("ok"):
            raise RuntimeError(health.get("detail") or "Camera health check failed.")
        handle = camera.start(session, _media_path(recording.raw_path))
        recording.camera_name = camera.name
        recording.capture_handle = {
            "token": handle.token,
            "metadata": handle.metadata,
        }
        recording.capture_started_at = timezone.now()
        recording.status = PackagingRecording.Status.RECORDING
        recording.error = ""
        recording.terminal_error_class = ""
        recording.save(
            update_fields=[
                "camera_name",
                "capture_handle",
                "capture_started_at",
                "status",
                "error",
                "terminal_error_class",
            ]
        )
    except Exception as exc:  # noqa: BLE001 - camera outage cannot block packing
        recording.status = PackagingRecording.Status.FAILED
        recording.error = str(exc)
        recording.terminal_error_class = exc.__class__.__name__
        recording.save(
            update_fields=["status", "error", "terminal_error_class"]
        )
    return recording


@transaction.atomic
def seal_recording(session, *, user=None) -> PackagingRecording:
    """Seal the recording clock and enqueue exactly one processing job."""
    if not session.completed_at:
        raise ValidationError("The packing session must be completed before sealing.")

    recording = getattr(session, "recording", None) or start_recording(session, user=user)
    recording = PackagingRecording.objects.select_for_update().get(pk=recording.pk)
    if recording.sealed_at is None:
        recording.sealed_at = session.completed_at
        recording.capture_stopped_at = timezone.now()
        if recording.status != PackagingRecording.Status.READY:
            recording.status = PackagingRecording.Status.QUEUED
        recording.next_attempt_at = timezone.now()
        recording.save(
            update_fields=[
                "sealed_at",
                "capture_stopped_at",
                "status",
                "next_attempt_at",
            ]
        )

    enqueue(
        PROCESS_RECORDING_KIND,
        str(recording.pk),
        {"recording_id": recording.pk},
        available_at=recording.next_attempt_at or timezone.now(),
        max_attempts=settings.PACKAGING_PROCESS_MAX_ATTEMPTS,
    )
    return recording


def _record_processing_failure(recording, item, exc) -> None:
    terminal = isinstance(exc, PermanentWorkError) or item.attempts >= item.max_attempts
    recording.status = (
        PackagingRecording.Status.FAILED
        if terminal
        else PackagingRecording.Status.RETRYING
    )
    recording.processing_attempts = item.attempts
    recording.error = str(exc)
    recording.terminal_error_class = exc.__class__.__name__ if terminal else ""
    recording.next_attempt_at = (
        None
        if terminal
        else timezone.now()
        + timedelta(seconds=retry_delay_seconds(item.attempts))
    )
    recording.save(
        update_fields=[
            "status",
            "processing_attempts",
            "error",
            "terminal_error_class",
            "next_attempt_at",
        ]
    )


def process_recording_work(item) -> PackagingRecording:
    """Stop/recover capture, compress once, and enqueue customer notifications."""
    recording = PackagingRecording.objects.select_related(
        "session__order"
    ).get(pk=item.payload["recording_id"])
    if recording.sealed_at is None:
        exc = PermanentWorkError("Recording has not been sealed.")
        _record_processing_failure(recording, item, exc)
        raise exc

    recording.status = PackagingRecording.Status.PROCESSING
    recording.processing_attempts = item.attempts
    recording.next_attempt_at = None
    recording.save(
        update_fields=["status", "processing_attempts", "next_attempt_at"]
    )

    raw_abs = _media_path(recording.raw_path)
    compressed_abs = _media_path(recording.compressed_path)
    try:
        if not recording.raw_checksum or not os.path.exists(raw_abs):
            camera = get_camera(recording.camera_name or None)
            handle = _capture_handle(recording)
            result = (
                camera.stop(recording.session, raw_abs, handle)
                if handle is not None
                else camera.recover(recording.session, raw_abs)
            )
            recording.duration_seconds = result.duration_seconds
            recording.raw_size_bytes = os.path.getsize(raw_abs)
            recording.raw_checksum = _checksum(raw_abs)
            recording.captured_at = timezone.now()
            recording.save(
                update_fields=[
                    "duration_seconds",
                    "raw_size_bytes",
                    "raw_checksum",
                    "captured_at",
                ]
            )

        if not recording.compressed_checksum or not os.path.exists(compressed_abs):
            _compress(raw_abs, compressed_abs)
        recording.compressed_size_bytes = os.path.getsize(compressed_abs)
        recording.compressed_checksum = _checksum(compressed_abs)
        recording.compressed_at = recording.compressed_at or timezone.now()
        if not recording.customer_link_token:
            recording.customer_link_token = customer_video_token(recording)
            recording.customer_link_issued_at = timezone.now()
        recording.save(
            update_fields=[
                "compressed_size_bytes",
                "compressed_checksum",
                "compressed_at",
                "customer_link_token",
                "customer_link_issued_at",
            ]
        )

        dispatch_notification(
            recording.session.order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=recording.sealed_at,
            event_key=f"packaging-recording:{recording.pk}",
            payload={
                "video_url": customer_video_url(
                    recording, token=recording.customer_link_token
                ),
                "duration_seconds": recording.duration_seconds,
            },
        )
    except Exception as exc:
        _record_processing_failure(recording, item, exc)
        raise

    recording.status = PackagingRecording.Status.READY
    recording.error = ""
    recording.terminal_error_class = ""
    recording.next_attempt_at = None
    recording.save(
        update_fields=[
            "status",
            "error",
            "terminal_error_class",
            "next_attempt_at",
        ]
    )
    return recording


def _retained_path(relative: str) -> Path | None:
    relative_path = Path(relative)
    if (
        not relative
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    unresolved = root / relative_path
    cursor = root
    for part in relative_path.parts:
        cursor /= part
        if cursor.is_symlink():
            return None
    candidate = unresolved.resolve(strict=False)
    if not candidate.is_relative_to(root):
        return None
    return candidate


def cleanup_packaging_media(*, now=None, dry_run: bool = False) -> dict:
    """Apply raw/compressed retention while retaining the audit rows."""
    now = now or timezone.now()
    raw_cutoff = now - timedelta(seconds=settings.PACKAGING_RAW_RETENTION_SECONDS)
    compressed_cutoff = now - timedelta(
        seconds=settings.PACKAGING_COMPRESSED_RETENTION_SECONDS
    )
    raw_due = list(
        PackagingRecording.objects.filter(
            raw_deleted_at__isnull=True,
            raw_path__gt="",
            captured_at__lte=raw_cutoff,
        )
    )
    compressed_due = list(
        PackagingRecording.objects.filter(
            compressed_deleted_at__isnull=True,
            compressed_path__gt="",
            compressed_at__lte=compressed_cutoff,
        )
    )
    report = {
        "raw_due": len(raw_due),
        "compressed_due": len(compressed_due),
        "pending": len(raw_due) + len(compressed_due),
        "deleted": 0,
        "missing": 0,
        "unsafe": 0,
        "configuration_errors": [],
    }
    if (
        settings.PACKAGING_COMPRESSED_RETENTION_SECONDS
        < settings.PACKAGING_LINK_TTL_SECONDS
    ):
        report["configuration_errors"].append(
            "Compressed retention is shorter than the customer-link TTL."
        )

    for recording, path_field, deleted_field in [
        *((row, "raw_path", "raw_deleted_at") for row in raw_due),
        *((row, "compressed_path", "compressed_deleted_at") for row in compressed_due),
    ]:
        candidate = _retained_path(getattr(recording, path_field))
        if candidate is None or (candidate.exists() and not candidate.is_file()):
            report["unsafe"] += 1
            continue
        if dry_run:
            continue
        if candidate.exists():
            candidate.unlink()
            report["deleted"] += 1
        else:
            report["missing"] += 1
        setattr(recording, deleted_field, now)
        recording.save(update_fields=[deleted_field])
    return report
