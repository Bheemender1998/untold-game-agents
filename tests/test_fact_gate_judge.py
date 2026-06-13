from engine.pipeline import fact_gate


def _items():
    return [
        ({"text": "Piquet crashed on lap 15", "entity": "x", "fact": "lap 15", "era": "encyclopedic"},
         {"kind": "encyclopedic", "text": "on the 15th lap Piquet crashed", "source": "Wikipedia: C"}),
        ({"text": "Symonds was technical director", "entity": "x", "fact": "technical director", "era": "encyclopedic"},
         {"kind": "encyclopedic", "text": "Symonds was executive director of engineering", "source": "Wikipedia: C"}),
    ]


def test_judge_maps_verdicts_by_index(monkeypatch):
    monkeypatch.setattr(fact_gate, "_structured", lambda *a, **k: {"verdicts": [
        {"index": 0, "verdict": "supported", "correction": "", "source": "Wikipedia: C"},
        {"index": 1, "verdict": "contradicted", "correction": "executive director of engineering", "source": "Wikipedia: C"},
    ]})
    out = fact_gate.judge(_items())
    assert out[0]["verdict"] == "supported" and out[0]["evidence_kind"] == "encyclopedic"
    assert out[1]["verdict"] == "contradicted" and out[1]["correction"]
    assert out[0]["claim"] == "Piquet crashed on lap 15"


def test_judge_missing_verdict_defaults_unverified(monkeypatch):
    monkeypatch.setattr(fact_gate, "_structured",
                        lambda *a, **k: {"verdicts": [{"index": 0, "verdict": "supported", "correction": "", "source": ""}]})
    out = fact_gate.judge(_items())
    assert out[1]["verdict"] == "unverified"


def test_judge_failure_fails_closed(monkeypatch):
    def boom(*a, **k): raise RuntimeError("api down")
    monkeypatch.setattr(fact_gate, "_structured", boom)
    out = fact_gate.judge(_items())
    assert [v["verdict"] for v in out] == ["unverified", "unverified"]


def test_judge_empty_returns_empty():
    assert fact_gate.judge([]) == []
