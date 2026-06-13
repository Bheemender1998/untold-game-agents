"""Single source of truth for produced-artifact locations.

Artifacts are namespaced by output format so a long and its companion short can
coexist for one idea without clobbering each other:

    produced/<id>/long/   script.md  metadata.json  factcheck.json  qc.json  video/
    produced/<id>/short/  script.md  metadata.json  factcheck.json  qc.json  video/
"""
from __future__ import annotations
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCED_DIR = os.path.join(_ROOT, "produced")
FORMATS = ("long", "short")


def artifact_dir(idea_id: str, fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return os.path.join(PRODUCED_DIR, idea_id, fmt)


def script_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "script.md")


def metadata_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "metadata.json")


def factcheck_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "factcheck.json")


def qc_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "qc.json")


def video_dir(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "video")


def thumbnail_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "thumbnail.jpg")


def subject_path(idea_id: str, fmt: str) -> str:
    """The human-supplied subject photo. Prefers subject.png, then subject.jpg;
    returns the .png path (which may not exist yet) when neither is present."""
    d = artifact_dir(idea_id, fmt)
    png = os.path.join(d, "subject.png")
    jpg = os.path.join(d, "subject.jpg")
    if os.path.exists(png):
        return png
    if os.path.exists(jpg):
        return jpg
    return png


# Channel-level (not per-idea) assets: the generated banner + description for manual upload.
CHANNEL_DIR = os.path.join(_ROOT, "channel")


def channel_banner_path() -> str:
    return os.path.join(CHANNEL_DIR, "banner.png")


def channel_description_path() -> str:
    return os.path.join(CHANNEL_DIR, "description.txt")
