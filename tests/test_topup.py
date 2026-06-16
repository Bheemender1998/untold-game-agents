import sys

from engine import run_pipeline
from engine import config


# ── Task 1: pure helper + config constant ──

def test_topup_needed_below_floor():
    assert run_pipeline._topup_needed(5, 12) is True


def test_topup_not_needed_above_floor():
    assert run_pipeline._topup_needed(20, 12) is False


def test_topup_not_needed_at_floor():
    # At exactly the floor we already have "enough" → skip (>= floor means skip).
    assert run_pipeline._topup_needed(12, 12) is False


def test_topup_min_config_default_is_twelve():
    # Default floor when IDEATE_TOPUP_MIN is unset.
    assert config.IDEATE_TOPUP_MIN == 12


# ── Task 2: --ensure-min flag + guard in main() ──

def _run_main(monkeypatch, argv, pending_count):
    """Drive run_pipeline.main() with a stubbed queue + spy on generation."""
    calls = {"all": 0, "single": 0}
    monkeypatch.setattr(sys, "argv", ["run_pipeline", *argv])
    monkeypatch.setattr(run_pipeline, "get_pending",
                        lambda *a, **k: [{"id": i} for i in range(pending_count)])
    monkeypatch.setattr(run_pipeline, "run_all_agents",
                        lambda *a, **k: calls.__setitem__("all", calls["all"] + 1))
    monkeypatch.setattr(run_pipeline, "run_single_agent",
                        lambda *a, **k: calls.__setitem__("single", calls["single"] + 1))
    monkeypatch.setattr(run_pipeline, "print_stats", lambda *a, **k: None)
    run_pipeline.main()
    return calls


def test_ensure_min_skips_generation_when_queue_full(monkeypatch):
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min"], pending_count=20)
    assert calls["all"] == 0 and calls["single"] == 0


def test_ensure_min_generates_when_queue_low(monkeypatch):
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min"], pending_count=5)
    assert calls["all"] == 1


def test_ensure_min_explicit_value_overrides_floor(monkeypatch):
    # Floor 3: 5 pending ≥ 3 → skip even though it's below the default 12.
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min", "3"], pending_count=5)
    assert calls["all"] == 0


def test_no_flag_always_generates(monkeypatch):
    # Today's behaviour preserved: no --ensure-min → generate regardless of depth.
    calls = _run_main(monkeypatch, ["--no-review"], pending_count=999)
    assert calls["all"] == 1
