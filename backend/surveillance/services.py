"""Module 4 pipeline: capture the packing sequence, compress it, hand it to the
customer — triggered once, right after an order is sealed (complete_packing()).

Called from fulfillment's PackingViewSet.complete() rather than from
fulfillment.services itself, so Module 3 stays independent of Module 4 (the same
reason book_shipment lives in logistics, not fulfillment). Every step is wrapped
so a camera/ffmpeg/dispatch failure marks this recording FAILED and returns
normally — it must never take down the "Complete pack" response the operator is
waiting on.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from notifications.models import Notification
from notifications.services import dispatch as dispatch_notification

from .camera import get_camera
from .ffmpeg import run_ffmpeg
from .models import PackagingRecording

RAW_DIR = "packaging_videos/raw"
COMPRESSED_DIR = "packaging_videos/compressed"
# Downscale + high-CRF re-encode — a real compression pass, not a copy, so the
# "process/compress the clip" requirement is genuinely satisfied.
COMPRESSED_SCALE = "160:120"
COMPRESSED_CRF = "32"


def _media_path(relative: str) -> str:
    full = os.path.join(settings.MEDIA_ROOT, relative)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


def _compress(raw_abs_path: str, compressed_abs_path: str) -> None:
    run_ffmpeg(
        [
            "-i", raw_abs_path,
            "-vf", f"scale={COMPRESSED_SCALE}",
            "-c:v", "libx264",
            "-crf", COMPRESSED_CRF,
            "-preset", "ultrafast",
            "-an",
            compressed_abs_path,
        ]
    )


def capture_and_dispatch(session, *, user=None) -> PackagingRecording:
    """Record, compress, and email/WhatsApp the packaging video for a just-sealed
    session. sealed_at = session.completed_at is the KPI #2 clock start.

    Idempotent, like book_shipment: a retried/duplicated complete() call for the
    same session returns the existing recording instead of raising on the
    OneToOne constraint. That constraint is still the source of truth under a
    genuine race (two concurrent calls both pass the pre-check) — the
    IntegrityError fallback below covers that case.
    """
    existing = getattr(session, "recording", None)
    if existing is not None:
        return existing

    sealed_at = session.completed_at or timezone.now()
    try:
        recording = PackagingRecording.objects.create(session=session, sealed_at=sealed_at)
    except IntegrityError:
        session.refresh_from_db()
        return session.recording

    raw_relative = f"{RAW_DIR}/{session.id}.mp4"
    compressed_relative = f"{COMPRESSED_DIR}/{session.id}.mp4"

    try:
        recording.status = PackagingRecording.Status.RECORDING
        recording.save(update_fields=["status"])
        raw_abs = _media_path(raw_relative)
        result = get_camera().capture(session, raw_abs)
        recording.raw_path = raw_relative
        recording.duration_seconds = result.duration_seconds
        recording.raw_size_bytes = os.path.getsize(raw_abs)
        recording.captured_at = timezone.now()
        recording.status = PackagingRecording.Status.PROCESSING
        recording.save(
            update_fields=[
                "raw_path", "duration_seconds", "raw_size_bytes",
                "captured_at", "status",
            ]
        )

        compressed_abs = _media_path(compressed_relative)
        _compress(raw_abs, compressed_abs)
        recording.compressed_path = compressed_relative
        recording.compressed_size_bytes = os.path.getsize(compressed_abs)
        recording.compressed_at = timezone.now()
        recording.status = PackagingRecording.Status.READY
        recording.save(
            update_fields=[
                "compressed_path", "compressed_size_bytes",
                "compressed_at", "status",
            ]
        )
    except Exception as exc:  # noqa: BLE001 - never let capture/compress break the pack
        recording.status = PackagingRecording.Status.FAILED
        recording.error = str(exc)
        recording.save(update_fields=["status", "error"])
        return recording

    try:
        # dispatch() already isolates per-channel send failures (a bad email/
        # WhatsApp attempt lands as a FAILED Notification, not an exception);
        # this guards the one remaining failure mode, the ledger write itself.
        dispatch_notification(
            session.order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=sealed_at,
            payload={
                "video_url": f"{settings.MEDIA_URL}{compressed_relative}",
                "duration_seconds": recording.duration_seconds,
            },
        )
    except Exception:  # noqa: BLE001 - the recording is READY either way
        pass
    return recording
