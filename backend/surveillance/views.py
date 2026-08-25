"""Authorized streaming endpoint for compressed packaging video."""

import mimetypes
import re
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import PackagingRecording
from .signing import verify_customer_video_token

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def _denied(detail: str = "Video access denied.") -> JsonResponse:
    return JsonResponse({"detail": detail}, status=403)


def _authorized(request, recording: PackagingRecording) -> bool:
    token = request.GET.get("token")
    if token is not None:
        return verify_customer_video_token(recording, token)
    user = request.user
    return bool(
        user.is_authenticated
        and (
            user.is_manager
            or recording.session.operator_id == user.pk
        )
    )


def _compressed_path(recording: PackagingRecording) -> Path | None:
    if (
        recording.status != PackagingRecording.Status.READY
        or not recording.compressed_path
    ):
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    relative = Path(recording.compressed_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            return None
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    if recording.compressed_checksum:
        digest = sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != recording.compressed_checksum:
            return None
    return candidate


def _range_response(request, path: Path, content_type: str):
    size = path.stat().st_size
    header = request.headers.get("Range")
    if not header:
        response = FileResponse(path.open("rb"), content_type=content_type)
        response["Content-Length"] = str(size)
        response["Accept-Ranges"] = "bytes"
        response["Content-Disposition"] = f'inline; filename="{path.name}"'
        return response

    match = _RANGE_RE.fullmatch(header.strip())
    if not match:
        response = JsonResponse({"detail": "Invalid byte range."}, status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    start_text, end_text = match.groups()
    if not start_text and not end_text:
        response = JsonResponse({"detail": "Invalid byte range."}, status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    if start_text:
        start = int(start_text)
        end = min(int(end_text), size - 1) if end_text else size - 1
    else:
        suffix = int(end_text)
        start = max(size - suffix, 0)
        end = size - 1
    if start >= size or start > end:
        response = JsonResponse({"detail": "Range outside file."}, status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response

    length = end - start + 1

    def chunks():
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    response = StreamingHttpResponse(chunks(), status=206, content_type=content_type)
    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = f'inline; filename="{path.name}"'
    return response


@require_GET
def recording_video(request, pk):
    recording = get_object_or_404(
        PackagingRecording.objects.select_related("session__operator"), pk=pk
    )
    if not _authorized(request, recording):
        return _denied()
    path = _compressed_path(recording)
    if path is None:
        return JsonResponse({"detail": "Video is not available."}, status=404)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return _range_response(request, path, content_type)
