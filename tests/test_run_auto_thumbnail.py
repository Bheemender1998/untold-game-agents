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


def _patch_thumb_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: {"id": _id})


def test_ensure_thumbnail_skips_when_thumbnail_exists(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    os.makedirs(paths.artifact_dir("pubid", "long"), exist_ok=True)
    from PIL import Image
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("pubid", "long"))
    calls = {"source": 0, "gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject",
                        lambda idea, fmt: calls.__setitem__("source", calls["source"] + 1) or {"source": "x"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")
    assert calls == {"source": 0, "gen": 0}   # neither called — thumbnail already present


def test_ensure_thumbnail_generates_when_missing(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    calls = {"gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": "wikipedia"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")
    assert calls["gen"] == 1


def test_ensure_thumbnail_self_stubs_when_no_photo(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    calls = {"gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": None, "path": "p"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")   # must not raise
    assert calls["gen"] == 0   # no subject → no generation


def test_ensure_thumbnail_swallows_exceptions(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": "pexels"})
    def boom(idea, fmt):
        raise RuntimeError("PIL exploded")
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail", boom)
    run_auto._ensure_thumbnail("pubid", "long")   # would ERROR if it propagated — no assertion needed


def test_render_and_qc_calls_ensure_thumbnail(monkeypatch):
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    from engine.pipeline import chapters
    monkeypatch.setattr(chapters, "sync_from_render", lambda i, fmt: False)
    monkeypatch.setattr(run_auto, "_companion_short", lambda i: None)
    seen = []
    monkeypatch.setattr(run_auto, "_ensure_thumbnail", lambda i, fmt: seen.append((i, fmt)))
    run_auto._render_and_qc("pubid")
    assert ("pubid", "long") in seen


def test_companion_short_calls_ensure_thumbnail(monkeypatch):
    monkeypatch.setattr(run_auto, "_produce_companion", lambda i: {"within_long": True})
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 0)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="short": {"passed": True, "checks": []})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    seen = []
    monkeypatch.setattr(run_auto, "_ensure_thumbnail", lambda i, fmt: seen.append((i, fmt)))
    run_auto._companion_short("pubid")
    assert ("pubid", "short") in seen


def test_render_and_qc_thumbnails_even_when_qc_fails(monkeypatch):
    # Thumbnail is independent of QC — it must fire even on a qc_failed long.
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": False, "checks": []})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    from engine.pipeline import chapters
    monkeypatch.setattr(chapters, "sync_from_render", lambda i, fmt: False)
    seen = []
    monkeypatch.setattr(run_auto, "_ensure_thumbnail", lambda i, fmt: seen.append((i, fmt)))
    run_auto._render_and_qc("pubid")
    assert ("pubid", "long") in seen   # thumbnail generated regardless of QC verdict


def test_cmd_approve_warns_when_thumbnail_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    monkeypatch.setattr(run_auto.uploader, "upload", lambda video_path, **kw: "VID123")
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    out = capsys.readouterr().out
    assert "no custom thumbnail" in out   # warns about default-frame upload
