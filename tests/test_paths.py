import os
import pytest
from engine import paths


def test_artifact_dir_is_format_namespaced():
    d = paths.artifact_dir("abc123", "long")
    assert d.endswith(os.path.join("produced", "abc123", "long"))


def test_artifact_dir_rejects_unknown_format():
    with pytest.raises(ValueError):
        paths.artifact_dir("abc123", "landscape")


def test_named_paths_sit_under_format_dir():
    assert paths.script_path("x", "short").endswith(
        os.path.join("produced", "x", "short", "script.md"))
    assert paths.metadata_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "metadata.json"))
    assert paths.factcheck_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "factcheck.json"))
    assert paths.qc_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "qc.json"))
    assert paths.video_dir("x", "long").endswith(
        os.path.join("produced", "x", "long", "video"))


def test_all_paths_share_artifact_dir_root():
    base = paths.artifact_dir("x", "long")
    for p in (paths.script_path("x", "long"), paths.metadata_path("x", "long"),
              paths.video_dir("x", "long")):
        assert p.startswith(base)
