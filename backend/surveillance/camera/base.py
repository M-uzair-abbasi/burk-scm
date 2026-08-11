"""Overhead-camera capture interface.

Mirrors orders/connectors and notifications/channels: a camera adapter only has
to produce a video file at a given path and report its duration. Swapping the
simulated feed for a real RTSP/USB overhead camera is a one-line change in
camera/__init__.py; capture_and_dispatch()'s compress/dispatch steps in
services.py don't change at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CaptureResult:
    duration_seconds: float


class CameraAdapter:
    name: str = ""

    def capture(self, session, out_path: str) -> CaptureResult:
        """Write a video of the packing sequence to out_path (absolute path)."""
        raise NotImplementedError
