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


def _mean_luma(path: str, every_n: int = 30) -> float | None:
    """Average YAVG (0-255) over every Nth frame via ffmpeg signalstats."""
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path,
             "-vf", f"select='not(mod(n\\,{every_n}))',signalstats,metadata=print:file=-",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError:
        return None
    vals = [float(m) for m in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", out.stdout)]
    return sum(vals) / len(vals) if vals else None


def brightness_band(video_path: str) -> dict:
    name = "brightness_band"
    luma = _mean_luma(video_path)
    if luma is None:
        return {"name": name, "passed": False, "detail": "could not read luma"}
    ok = config.QC_BRIGHTNESS_MIN <= luma <= config.QC_BRIGHTNESS_MAX
    return {"name": name, "passed": ok,
            "detail": f"mean luma={luma:.0f} band=[{config.QC_BRIGHTNESS_MIN:.0f},{config.QC_BRIGHTNESS_MAX:.0f}]"}


def caption_coverage(props_path: str, audio_dur: float) -> dict:
    """Pass = caption words reach ≥ QC_MIN_CAPTION_COVERAGE of the audio AND no inter-word
    gap exceeds QC_MAX_CAPTION_GAP_S. Reads props.json['captions'] ({text,startMs,endMs})."""
    name = "caption_coverage"
    try:
        caps = json.load(open(props_path)).get("captions", [])
    except (OSError, ValueError):
        return {"name": name, "passed": False, "detail": "props.json unreadable"}
    if not caps or not audio_dur:
        return {"name": name, "passed": False, "detail": "no captions or zero audio"}
    caps = sorted(caps, key=lambda c: c["startMs"])
    last_end_s = max(c["endMs"] for c in caps) / 1000.0
    coverage = last_end_s / audio_dur
    max_gap_s = max([(caps[i + 1]["startMs"] - caps[i]["endMs"]) / 1000.0
                     for i in range(len(caps) - 1)] or [0.0])
    ok = coverage >= config.QC_MIN_CAPTION_COVERAGE and max_gap_s <= config.QC_MAX_CAPTION_GAP_S
    return {"name": name, "passed": ok,
            "detail": f"coverage={coverage:.0%} max_gap={max_gap_s:.1f}s"}
