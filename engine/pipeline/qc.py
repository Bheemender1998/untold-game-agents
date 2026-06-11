"""Local quality gate for a rendered video. ffprobe/ffmpeg only — no network, no API.
Each check returns {'name', 'passed', 'detail'}; qc_video() ANDs them and writes qc.json."""
from __future__ import annotations
import json
import os
import re
import subprocess

from engine import config

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ffprobe_duration(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def _ffprobe_stream_types(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except subprocess.SubprocessError:
        return set()


def render_integrity(video_path: str, audio_path: str) -> dict:
    """Pass = file exists, has video+audio streams, and its duration is within
    QC_DURATION_TOLERANCE of the narration audio (the ground-truth length)."""
    name = "render_integrity"
    if not os.path.exists(video_path):
        return {"name": name, "passed": False, "detail": "video.mp4 missing"}
    streams = _ffprobe_stream_types(video_path)
    if not {"video", "audio"} <= streams:
        return {"name": name, "passed": False, "detail": f"streams={sorted(streams)}"}
    v_dur, a_dur = _ffprobe_duration(video_path), _ffprobe_duration(audio_path)
    if v_dur is None or a_dur is None or a_dur == 0:
        return {"name": name, "passed": False, "detail": f"unreadable durations v={v_dur} a={a_dur}"}
    drift = abs(v_dur - a_dur) / a_dur
    ok = drift <= config.QC_DURATION_TOLERANCE
    return {"name": name, "passed": ok,
            "detail": f"video={v_dur:.1f}s audio={a_dur:.1f}s drift={drift:.0%}"}
