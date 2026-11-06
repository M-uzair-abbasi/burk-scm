"""Simulated overhead workspace camera.

There is no physical overhead camera wired into this dev environment, so this
adapter synthesizes a short clip with ffmpeg (a real, playable MP4 — genuinely
generated and genuinely compressible, just not real footage) rather than faking
a file. It stands in exactly where a real camera's frame grabber would sit;
live_camera.py is the documented drop-in once hardware exists.
"""

from __future__ import annotations

import shutil
import uuid

from ..ffmpeg import run_ffmpeg
from .base import CameraAdapter, CaptureHandle, CaptureResult

DURATION_SECONDS = 3.0
RESOLUTION = "320x240"
FRAME_RATE = 15


class SimulatedOverheadCameraAdapter(CameraAdapter):
    name = "simulated"

    def health(self) -> dict:
        return {
            "ok": shutil.which("ffmpeg") is not None,
            "mode": "simulated",
            "adapter": self.name,
        }

    def start(self, session, out_path: str) -> CaptureHandle:
        # Deliberately lightweight: the request records a capture handle; the
        # worker materializes the deterministic clip only after the pack seals.
        return CaptureHandle(token=f"sim-{session.pk}-{uuid.uuid4().hex}")

    def stop(
        self, session, out_path: str, handle: CaptureHandle
    ) -> CaptureResult:
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

    def recover(
        self, session, out_path: str, handle: CaptureHandle | None = None
    ) -> CaptureResult:
        return self.stop(
            session,
            out_path,
            handle or CaptureHandle(token=f"recovered-{session.pk}"),
        )
