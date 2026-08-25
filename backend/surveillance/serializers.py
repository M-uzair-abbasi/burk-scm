from django.urls import reverse

from .models import PackagingRecording


def recording_detail(
    recording: PackagingRecording | None, *, include_error: bool = True
) -> dict | None:
    """Everything the packing station needs to show the video/dispatch panel."""
    if recording is None:
        return None
    return {
        "id": recording.id,
        "status": recording.status,
        "status_display": recording.get_status_display(),
        "video_url": (
            reverse("recording-video", args=[recording.pk])
            if recording.status == PackagingRecording.Status.READY
            and recording.compressed_path
            else None
        ),
        "duration_seconds": recording.duration_seconds,
        "raw_size_bytes": recording.raw_size_bytes,
        "compressed_size_bytes": recording.compressed_size_bytes,
        "raw_checksum": recording.raw_checksum,
        "compressed_checksum": recording.compressed_checksum,
        "sealed_at": recording.sealed_at,
        "capture_started_at": recording.capture_started_at,
        "capture_stopped_at": recording.capture_stopped_at,
        "captured_at": recording.captured_at,
        "compressed_at": recording.compressed_at,
        "processing_attempts": recording.processing_attempts,
        "next_attempt_at": recording.next_attempt_at,
        "error": recording.error if include_error else "",
        "terminal_error_class": (
            recording.terminal_error_class if include_error else ""
        ),
        "raw_deleted_at": recording.raw_deleted_at,
        "compressed_deleted_at": recording.compressed_deleted_at,
    }
