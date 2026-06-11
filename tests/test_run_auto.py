import time

from engine import run_auto


def test_select_returns_top_n_pending(monkeypatch):
    pending = [{"id": "a"}, {"id": "b"}, {"id": "c"}]  # get_pending() already sorts by score
    monkeypatch.setattr(run_auto.q, "get_pending", lambda: pending)
    assert [i["id"] for i in run_auto._select(2)] == ["a", "b"]


def test_produce_one_returns_resulting_status(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 0)  # produce subprocess "succeeds"
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": i, "status": "in_production", "human_reviewed": False})
    assert run_auto._produce_one("x") == "in_production"


def test_run_kills_on_timeout():
    start = time.monotonic()
    rc = run_auto._run(["sleep", "10"], timeout=1)
    assert rc == 124
    assert time.monotonic() - start < 5  # killed promptly, not after 10s


def test_render_one_marks_render_failed_on_nonzero(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 1)
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    assert run_auto._render_one("x") is False
    assert seen["status"] == "render_failed"


def _stub_pipeline(monkeypatch, idea, render_ok=True, qc_pass=True):
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: idea["status"])
    monkeypatch.setattr(run_auto, "_render_one", lambda i: render_ok)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i: {"passed": qc_pass, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    return seen


def test_pipeline_marks_awaiting_approval_on_qc_pass(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_human_reviewed_clears_to_render(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": True}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_skips_unreviewed_needs_review(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": False}
    called = {"render": False}
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: "needs_review")
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_render_one",
                        lambda i: called.__setitem__("render", True) or True)
    run_auto.pipeline(count=1, no_render=False)
    assert called["render"] is False  # never rendered an unreviewed needs_review idea


def test_pipeline_marks_qc_failed(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=False)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "qc_failed"
