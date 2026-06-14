import os
from PIL import Image
from engine.pipeline import subject as S
from engine import paths


def _mk(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("idA", "short")
    os.makedirs(d, exist_ok=True)
    return d


def test_human_photo_wins(tmp_path, monkeypatch):
    d = _mk(tmp_path, monkeypatch)
    Image.new("RGB", (100, 100), (1, 2, 3)).save(os.path.join(d, "subject.png"))
    called = {"q": False}
    monkeypatch.setattr(S, "_subject_query", lambda *a: (called.__setitem__("q", True), ("", ""))[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "human"
    assert called["q"] is False  # never even queried


def test_person_uses_wikipedia(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("Felipe Massa", "formula 1 car"))
    monkeypatch.setattr(S.wikipedia, "lead_image", lambda q: ("http://x/m.jpg", "Jane / CC BY via Wikimedia Commons"))
    monkeypatch.setattr(S, "_download", lambda url, out: (open(out, "wb").write(b"x"), True)[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "wikipedia"
    assert "Jane" in res["credit"]
    assert os.path.exists(os.path.join(paths.artifact_dir("idA", "short"), "subject_credit.txt"))


def test_no_person_falls_back_to_pexels(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("", "fifa world cup trophy"))
    monkeypatch.setattr(S.wikipedia, "lead_image", lambda q: None)
    monkeypatch.setattr(S.footage, "fetch_photo", lambda q, out, **k: (open(out, "wb").write(b"x"), "Photo by Ann on Pexels")[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "pexels" and "Ann" in res["credit"]


def test_nothing_found_returns_none(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("", ""))
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] is None


def test_run_subject_main_reports(tmp_path, monkeypatch, capsys):
    import sys
    from engine import queue_manager, run_subject
    from engine.pipeline import subject as S2
    monkeypatch.setattr(queue_manager, "get_by_id", lambda i: {"id": i})
    monkeypatch.setattr(S2, "source_subject",
                        lambda idea, fmt: {"source": "wikipedia", "path": "p", "credit": "Jane / CC"})
    monkeypatch.setattr(sys, "argv", ["run_subject", "--id", "idA", "--format", "short"])
    run_subject.main()
    out = capsys.readouterr().out.lower()
    assert "wikipedia" in out and "jane" in out
