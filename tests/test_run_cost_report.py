import json

from engine import run_cost_report as rcr


def _seed(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_summarize_filters_by_run(tmp_path):
    led = tmp_path / "c.jsonl"
    _seed(led, [
        {"run_id": "A", "stage": "script_writer", "input_tokens": 1000,
         "output_tokens": 2000, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0, "cost_usd": 3.0},
        {"run_id": "A", "stage": "script_writer", "input_tokens": 0,
         "output_tokens": 0, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0, "cost_usd": 1.0},
        {"run_id": "B", "stage": "metadata", "input_tokens": 5, "output_tokens": 5,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "cost_usd": 99.0},
    ])
    agg = rcr.summarize(list(rcr._rows(str(led))), "A")
    assert set(agg) == {"script_writer"}
    assert agg["script_writer"]["calls"] == 2
    assert agg["script_writer"]["cost"] == 4.0


def test_render_total_no_warning_under_cap(monkeypatch):
    monkeypatch.setattr(rcr.config, "COST_ALERT_USD", 10.0)
    agg = {"metadata": {"calls": 1, "input": 1000, "output": 2000, "cost": 5.0}}
    out = rcr.render(agg, "A")
    assert "TOTAL" in out
    assert "$5.00" in out
    assert "BUDGET" not in out


def test_render_warning_over_cap(monkeypatch):
    monkeypatch.setattr(rcr.config, "COST_ALERT_USD", 10.0)
    agg = {"script_writer": {"calls": 3, "input": 1, "output": 1, "cost": 12.4}}
    out = rcr.render(agg, "A")
    assert "BUDGET" in out
    assert "$12.40 exceeds $10.00" in out


def test_render_empty_says_no_data():
    out = rcr.render({}, "A")
    assert "no cost data" in out
