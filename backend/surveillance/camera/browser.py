"""Browser-camera capture: the packer's own device, not dedicated hardware.

Validated as the production choice over an overhead workstation camera (no
hardware to buy or mount, works on a phone or the packing PC's webcam
unchanged). The capture itself happens entirely client-side via the browser's
MediaRecorder API; the server's only job is to receive the finished clip
through surveillance.services.save_uploaded_recording() and land it at the
raw_path this adapter's start() already reserved.

This inverts the push/pull direction the CameraAdapter interface was written
for: start()/stop() normally drive a server-attached device, but here the
device is the browser's, so start() is a no-op and stop()/recover() just wait
for the upload to exist at out_path, letting the durable worker's existing
retry/backoff handle the ordinary case where the upload is still in flight
when the pack is sealed.
"""

from __future__ import annotations

import os
import uuid

from ..ffmpeg import probe_duration_seconds
from .base import CameraAdapter, CaptureHandle, CaptureResult


class BrowserCameraAdapter(CameraAdapter):
    name = "browser"

    def health(self) -> dict:
        # Nothing server-side to check: the camera is the packer's own device,
        # and its availability is a browser permission prompt, not a server
        # readiness concern.
        return {"ok": True, "mode": "live", "adapter": self.name}

    def start(self, session, out_path: str) -> CaptureHandle:
        return CaptureHandle(token=f"browser-{session.pk}-{uuid.uuid4().hex}")

    def stop(
        self, session, out_path: str, handle: CaptureHandle
    ) -> CaptureResult:
        return self._materialize(out_path)

    def recover(
        self, session, out_path: str, handle: CaptureHandle | None = None
    ) -> CaptureResult:
        return self._materialize(out_path)

    @staticmethod
    def _materialize(out_path: str) -> CaptureResult:
        if not os.path.exists(out_path):
            # Retryable, not terminal: process_recording_work's generic except
            # clause treats this as a transient failure and backs off, which is
            # exactly right for "the browser's upload hasn't landed yet."
            raise RuntimeError(
                "Browser recording has not been uploaded for this pack yet."
            )
        return CaptureResult(duration_seconds=probe_duration_seconds(out_path))
