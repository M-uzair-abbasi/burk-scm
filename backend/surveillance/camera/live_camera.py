"""Placeholder for a real overhead workspace camera.

The documented drop-in for production, same role as
orders/connectors/live_daraz.py and notifications/channels/live_whatsapp.py. To
activate: implement capture() to pull from an RTSP stream or a USB/V4L2 device
for the packing station's actual duration (start recording in the packing view
when the session begins, stop and save when complete_packing() fires) via
`ffmpeg -f v4l2 -i /dev/video0 ...` or an RTSP `-i rtsp://...` input, then
register this class instead of SimulatedOverheadCameraAdapter in camera/__init__.py.
"""

from __future__ import annotations

from common.integrations import pending_live_health

from .base import CameraAdapter, CaptureHandle, CaptureResult


class LiveOverheadCameraAdapter(CameraAdapter):
    name = "live"

    def health(self) -> dict:
        return pending_live_health(self.name, "PACKAGING_CAMERA_SOURCE")

    def start(self, session, out_path: str) -> CaptureHandle:
        raise NotImplementedError(
            "Live overhead camera capture requires physical hardware (RTSP/USB "
            "feed). Implement the ffmpeg -f v4l2 / -f rtsp start hook here."
        )

    def stop(
        self, session, out_path: str, handle: CaptureHandle
    ) -> CaptureResult:
        raise NotImplementedError("Implement camera stop/finalize for this device.")

    def recover(
        self, session, out_path: str, handle: CaptureHandle | None = None
    ) -> CaptureResult:
        raise NotImplementedError("Implement interrupted-capture recovery.")
