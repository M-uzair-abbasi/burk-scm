from django.conf import settings

from .models import PackagingRecording


def recording_detail(recording: PackagingRecording | None) -> dict | None:
    """Everything the packing station needs to show the video/dispatch panel."""
    if recording is None:
        return None
    return {
        "id": recording.id,
        "status": recording.status,
        "status_display": recording.get_status_display(),
        "video_url": (
            f"{settings.MEDIA_URL}{recording.compressed_path}"
            if recording.compressed_path
            else None
        ),
        "duration_seconds": recording.duration_seconds,
        "raw_size_bytes": recording.raw_size_bytes,
        "compressed_size_bytes": recording.compressed_size_bytes,
        "sealed_at": recording.sealed_at,
        "captured_at": recording.captured_at,
        "compressed_at": recording.compressed_at,
        "error": recording.error,
    }
