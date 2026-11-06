"""Overhead-camera capture interface.

Mirrors orders/connectors and notifications/channels: adapters expose health,
start, stop, and recovery while the shared durable worker owns compression and
notification hand-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaptureResult:
    duration_seconds: float


@dataclass
class CaptureHandle:
    token: str
    metadata: dict = field(default_factory=dict)


class CameraAdapter:
    name: str = ""

    def health(self) -> dict:
        """Return an adapter-specific health result containing at least `ok`."""
        raise NotImplementedError

    def start(self, session, out_path: str) -> CaptureHandle:
        """Begin capture without waiting for the packing session to finish."""
        raise NotImplementedError

    def stop(
        self, session, out_path: str, handle: CaptureHandle
    ) -> CaptureResult:
        """Seal the capture and materialize its raw video at `out_path`."""
        raise NotImplementedError

    def recover(
        self, session, out_path: str, handle: CaptureHandle | None = None
    ) -> CaptureResult:
        """Recover raw footage after a worker/process interruption."""
        raise NotImplementedError
