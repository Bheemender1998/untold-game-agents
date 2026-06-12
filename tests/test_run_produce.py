from engine import run_produce


def _stub_common(monkeypatch):
    """Stub out disk writes and the fact-gate so produce() runs without I/O or API calls."""
    monkeypatch.setattr(run_produce, "_atomic_write", lambda *a, **k: None)
    monkeypatch.setattr(run_produce.os.path, "exists", lambda p: False)
    monkeypatch.setattr(run_produce.os, "makedirs", lambda *a, **k: None)
    import engine.pipeline.factcheck as fc
    monkeypatch.setattr(fc, "factcheck",
                        lambda *a, **k: {"passed": True, "issues": [], "checked": 1, "complete": True})
    updates = []
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: updates.append(f))
    return updates


def _idea():
    return {"id": "s1", "title_variants": ["The Own Goal That Cost Him His Life"],
            "hook": "h", "pillar": "sport_vs_world", "sport": "Soccer",
            "target_audience": "fans", "why_it_works": "w"}


def test_short_uses_short_writer_and_stores_mood(monkeypatch):
    updates = _stub_common(monkeypatch)
    calls = {}
    def _short_writer(idea):
        calls["short"] = True
        return {"script": "Hook. Fact. Payoff.", "mood": "tense"}
    monkeypatch.setattr(run_produce, "generate_short_script", _short_writer)
    monkeypatch.setattr(run_produce, "generate_script",
                        lambda idea: (_ for _ in ()).throw(AssertionError("long-form writer must NOT run in --short")))
    monkeypatch.setattr(run_produce, "_short_metadata", lambda idea, s: {"title": "t", "description": "#Shorts", "tags": ["Shorts"]})
    monkeypatch.setattr(run_produce, "generate_metadata",
                        lambda idea, s: (_ for _ in ()).throw(AssertionError("long-form metadata must NOT run in --short")))
    run_produce.produce(_idea(), short=True)
    assert calls.get("short") is True
    assert any(f.get("mood") == "tense" for f in updates), "mood must be stored on the idea"


def test_short_writes_minimal_shorts_metadata(monkeypatch):
    _stub_common(monkeypatch)
    monkeypatch.setattr(run_produce, "generate_short_script",
                        lambda idea: {"script": "The own goal that cost him his life.", "mood": "tense"})
    written = {}
    monkeypatch.setattr(run_produce, "generate_metadata",
                        lambda idea, s: (_ for _ in ()).throw(AssertionError("must not call long-form metadata")))
    # capture the meta dict by patching json.dumps used at the metadata write
    real_meta = run_produce._short_metadata(_idea(), "The own goal that cost him his life.")
    assert real_meta["title"] == "The Own Goal That Cost Him His Life"
    assert "#Shorts" in real_meta["description"]
    assert "Shorts" in real_meta["tags"]


def test_long_form_still_uses_long_writer(monkeypatch):
    _stub_common(monkeypatch)
    calls = {}
    def _long_writer(idea):
        calls["long"] = True
        return "## Cold Open\nLong script."
    monkeypatch.setattr(run_produce, "generate_script", _long_writer)
    monkeypatch.setattr(run_produce, "generate_metadata", lambda idea, s: {"title": "t"})
    monkeypatch.setattr(run_produce, "generate_short_script",
                        lambda idea: (_ for _ in ()).throw(AssertionError("short writer must NOT run without --short")))
    run_produce.produce(_idea(), short=False)
    assert calls.get("long") is True
