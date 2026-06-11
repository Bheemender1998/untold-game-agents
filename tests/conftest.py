"""Hermetic media fixtures built with ffmpeg — no dependency on any real render
(produced/ is gitignored, so committed renders are not available in CI)."""
import shutil
import subprocess

import pytest

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True, timeout=60)


@pytest.fixture
def gray_video(tmp_path):
    """2s mid-grey (luma ~126) clip WITH an audio track — passes brightness."""
    out = tmp_path / "video.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:d=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture
def black_video(tmp_path):
    """2s near-black (luma ~16) clip with audio — fails brightness_band."""
    out = tmp_path / "black.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:d=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture
def silent_audio(tmp_path):
    """2s wav — the narration-duration ground truth."""
    out = tmp_path / "narration.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:d=2", str(out))
    return out
