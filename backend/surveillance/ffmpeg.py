"""Thin subprocess wrapper around the system ffmpeg binary.

Shared by the simulated camera (clip generation) and services.compress() (real
re-encoding) so there is exactly one place that knows how to invoke ffmpeg and
turn a failure into a readable error.
"""

from __future__ import annotations

import subprocess

FFMPEG_TIMEOUT_SECONDS = 30

# Magic-byte signatures for the two containers this system ever produces or
# accepts: ffmpeg's own generated clips (simulated adapter, compression
# output) and a browser MediaRecorder's output (webm, or mp4 on Safari).
_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"


def detect_container(path: str) -> str:
    """Identify a media file's container from its own bytes, never its name.

    Raw clips reaching this module can originate from a browser upload --
    untrusted input, not just ffmpeg's own output. Letting ffmpeg/ffprobe
    auto-probe the container from content (the default) is exactly the
    mechanism behind known ffmpeg SSRF/local-file-read bugs, where a crafted
    file masquerading as a video is actually a concat/HLS script that makes
    ffmpeg follow a URL or path it was never meant to touch. Pinning the
    input format here, instead of letting ffmpeg guess, closes that off.
    """
    with open(path, "rb") as stream:
        header = stream.read(12)
    if header.startswith(_WEBM_MAGIC):
        return "webm"
    if header[4:8] == b"ftyp":
        return "mp4"
    raise RuntimeError(f"Unrecognized or unsupported media container: {path}")


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


def probe_duration_seconds(path: str) -> float:
    """Read a media file's duration via ffprobe.

    Used by the browser camera adapter: unlike the simulated/live-hardware
    adapters, which choose their own clip length, a browser upload's duration
    is whatever the packer actually recorded and has to be read back from the
    file itself.
    """
    container = detect_container(path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-protocol_whitelist", "file",
            "-f", container,
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed ({result.returncode}): {result.stderr.strip()}")
    return float(result.stdout.strip())
