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
