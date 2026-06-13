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


def test_thumbnail_path_under_artifact_dir():
    p = paths.thumbnail_path("abc123", "short")
    assert p == os.path.join(paths.artifact_dir("abc123", "short"), "thumbnail.jpg")


def test_subject_path_prefers_png_then_jpg(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("id1", "long")
    os.makedirs(d, exist_ok=True)
    # nothing present yet -> default .png path
    assert paths.subject_path("id1", "long").endswith("subject.png")
    # a .jpg present and no .png -> returns the .jpg
    open(os.path.join(d, "subject.jpg"), "w").close()
    assert paths.subject_path("id1", "long").endswith("subject.jpg")
    # a .png present -> .png wins
    open(os.path.join(d, "subject.png"), "w").close()
    assert paths.subject_path("id1", "long").endswith("subject.png")
