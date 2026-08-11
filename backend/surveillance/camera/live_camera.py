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

from .base import CameraAdapter, CaptureResult


class LiveOverheadCameraAdapter(CameraAdapter):
    name = "live"

    def capture(self, session, out_path: str) -> CaptureResult:
        raise NotImplementedError(
            "Live overhead camera capture requires physical hardware (RTSP/USB "
            "feed) and a recording-start hook at start_packing(). Implement the "
            "ffmpeg -f v4l2 / -f rtsp capture here."
        )
