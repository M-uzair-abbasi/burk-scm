"""Camera adapter registry. Mirrors orders/connectors and notifications/channels."""

from django.conf import settings

from common.integrations import require_demo_mode

from .base import CameraAdapter, CaptureHandle, CaptureResult
from .simulated import SimulatedOverheadCameraAdapter
from .live_camera import LiveOverheadCameraAdapter

CAMERAS = {
    "simulated": SimulatedOverheadCameraAdapter,
    "live": LiveOverheadCameraAdapter,
}

__all__ = [
    "CameraAdapter",
    "CaptureHandle",
    "CaptureResult",
    "CAMERAS",
    "get_camera",
]


def get_camera(name: str | None = None) -> CameraAdapter:
    name = name or settings.PACKAGING_CAMERA_BACKEND
    if name == "simulated":
        require_demo_mode("packaging camera")
    try:
        camera_cls = CAMERAS[name]
    except KeyError:
        raise ValueError(f"Unknown camera adapter: {name!r}")
    return camera_cls()
