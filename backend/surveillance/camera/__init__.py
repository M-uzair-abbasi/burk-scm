"""Camera adapter registry. Mirrors orders/connectors and notifications/channels."""

from .base import CameraAdapter, CaptureResult
from .simulated import SimulatedOverheadCameraAdapter

CAMERAS = {
    "simulated": SimulatedOverheadCameraAdapter,
}

__all__ = ["CameraAdapter", "CaptureResult", "CAMERAS", "get_camera"]


def get_camera(name: str = "simulated") -> CameraAdapter:
    try:
        camera_cls = CAMERAS[name]
    except KeyError:
        raise ValueError(f"Unknown camera adapter: {name!r}")
    return camera_cls()
