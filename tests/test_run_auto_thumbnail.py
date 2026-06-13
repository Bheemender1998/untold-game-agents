import os
from engine import run_auto, paths


def _idea(tmp):
    d = paths.artifact_dir("pubid", "long")
    os.makedirs(os.path.join(d, "video"), exist_ok=True)
    open(os.path.join(d, "video", "final.mp4"), "w").close()
    open(paths.metadata_path("pubid", "long"), "w").write('{"title":"T","description":"d","tags":[]}')
    root = os.path.dirname(paths.PRODUCED_DIR)
    return {"id": "pubid", "status": "awaiting_approval",
            "metadata_path": os.path.relpath(paths.metadata_path("pubid", "long"), root),
            "video_path": os.path.relpath(os.path.join(d, "video", "final.mp4"), root)}


def test_cmd_approve_passes_thumbnail_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    from PIL import Image
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("pubid", "long"))
    captured = {}
    def fake_upload(video_path, **kw):
        captured.update(kw)
        return "VID123"
    monkeypatch.setattr(run_auto.uploader, "upload", fake_upload)
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    assert captured.get("thumbnail_path") == paths.thumbnail_path("pubid", "long")


def test_cmd_approve_omits_thumbnail_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    captured = {}
    monkeypatch.setattr(run_auto.uploader, "upload", lambda video_path, **kw: captured.update(kw) or "VID123")
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    assert captured.get("thumbnail_path") is None
