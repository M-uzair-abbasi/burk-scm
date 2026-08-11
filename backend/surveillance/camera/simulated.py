"""Simulated overhead workspace camera.

There is no physical overhead camera wired into this dev environment, so this
adapter synthesizes a short clip with ffmpeg (a real, playable MP4 — genuinely
generated and genuinely compressible, just not real footage) rather than faking
a file. It stands in exactly where a real camera's frame grabber would sit;
live_camera.py is the documented drop-in once hardware exists.
"""

from __future__ import annotations

from ..ffmpeg import run_ffmpeg
from .base import CameraAdapter, CaptureResult

DURATION_SECONDS = 3.0
RESOLUTION = "320x240"
FRAME_RATE = 15


class SimulatedOverheadCameraAdapter(CameraAdapter):
    name = "simulated"

    def capture(self, session, out_path: str) -> CaptureResult:
        run_ffmpeg(
            [
                "-f", "lavfi",
                "-i", f"testsrc2=size={RESOLUTION}:rate={FRAME_RATE}:duration={DURATION_SECONDS}",
                "-pix_fmt", "yuv420p",
                "-preset", "ultrafast",
                "-an",
                out_path,
            ]
        )
        return CaptureResult(duration_seconds=DURATION_SECONDS)
