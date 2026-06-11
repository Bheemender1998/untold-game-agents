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
