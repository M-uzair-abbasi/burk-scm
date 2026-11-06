"""Short-lived, checksum-bound customer links for compressed pack videos."""

from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.urls import reverse

from .models import PackagingRecording

SIGNING_SALT = "burk-scm.packaging-video.v1"


def customer_video_token(recording: PackagingRecording) -> str:
    return signing.dumps(
        {
            "recording_id": recording.pk,
            "checksum": recording.compressed_checksum,
        },
        salt=SIGNING_SALT,
        compress=True,
    )


def verify_customer_video_token(recording: PackagingRecording, token: str) -> bool:
    try:
        payload = signing.loads(
            token,
            salt=SIGNING_SALT,
            max_age=settings.PACKAGING_LINK_TTL_SECONDS,
        )
    except signing.BadSignature:
        return False
    return (
        payload.get("recording_id") == recording.pk
        and bool(recording.compressed_checksum)
        and payload.get("checksum") == recording.compressed_checksum
    )


def customer_video_url(
    recording: PackagingRecording, *, token: str | None = None
) -> str:
    path = reverse("recording-video", args=[recording.pk])
    query = urlencode({"token": token or customer_video_token(recording)})
    return f"{settings.PUBLIC_APP_ORIGIN.rstrip('/')}{path}?{query}"
