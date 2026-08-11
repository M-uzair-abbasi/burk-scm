"""Thin subprocess wrapper around the system ffmpeg binary.

Shared by the simulated camera (clip generation) and services.compress() (real
re-encoding) so there is exactly one place that knows how to invoke ffmpeg and
turn a failure into a readable error.
"""

from __future__ import annotations

import subprocess

FFMPEG_TIMEOUT_SECONDS = 30


def run_ffmpeg(args: list[str]) -> None:
    """Run `ffmpeg <args>`, raising RuntimeError with stderr on failure."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()}")
