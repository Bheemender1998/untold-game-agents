from engine import run_produce


def _stub_common(monkeypatch):
    """Stub out disk writes and the fact-gate so produce() runs without I/O or API calls."""
    monkeypatch.setattr(run_produce, "_atomic_write", lambda *a, **k: None)
    monkeypatch.setattr(run_produce.os.path, "exists", lambda p: False)
    monkeypatch.setattr(run_produce.os, "makedirs", lambda *a, **k: None)
    import engine.pipeline.factcheck as fc
    monkeypatch.setattr(fc, "factcheck",
                        lambda *a, **k: {"passed": True, "issues": [], "checked": 1, "complete": True})
    monkeypatch.setattr(run_produce, "_append_shadow", lambda rec: None)
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
    monkeypatch.setattr(run_produce, "generate_short_metadata", lambda idea, s: {"title": "t", "description": "#Shorts", "tags": ["Shorts"]})
    monkeypatch.setattr(run_produce, "generate_metadata",
                        lambda idea, s: (_ for _ in ()).throw(AssertionError("long-form metadata must NOT run in --short")))
    run_produce.produce(_idea(), fmt="short")
    assert calls.get("short") is True
    assert any(f.get("mood") == "tense" for f in updates), "mood must be stored on the idea"


def test_short_writes_minimal_shorts_metadata(monkeypatch):
    # generate_short_metadata (now in pipeline.metadata) builds the Short's metadata;
    # stub the LLM calls so the test is offline and deterministic.
    from engine.pipeline import metadata
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda idea, s: ("A hook that pulls you in.", ["goal"]))
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
    real_meta = run_produce.generate_short_metadata(_idea(), "The own goal that cost him his life.")
    assert real_meta["title"] == "The Own Goal That Cost Him His Life"
    assert "#Shorts" in real_meta["description"]
    assert "Shorts" in real_meta["tags"]


def test_short_empty_script_raises(monkeypatch):
    import pytest
    _stub_common(monkeypatch)
    monkeypatch.setattr(run_produce, "generate_short_script", lambda idea: {"script": "   ", "mood": "tense"})
    with pytest.raises(ValueError):
        run_produce.produce(_idea(), fmt="short")


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
    run_produce.produce(_idea(), fmt="long")
    assert calls.get("long") is True


def test_produce_writes_under_long_subdir(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: True)
    monkeypatch.setattr(run_produce, "generate_script", lambda idea: "Long body words here.")
    monkeypatch.setattr(run_produce, "generate_metadata",
                        lambda idea, s: {"title": "T", "description": "D", "tags": []})
    idea = {"id": "zz", "title_variants": ["My Title"]}
    run_produce.produce(idea, factcheck_enabled=False, fmt="long")
    assert (tmp_path / "produced" / "zz" / "long" / "script.md").exists()
    assert (tmp_path / "produced" / "zz" / "long" / "metadata.json").exists()


def test_produce_companion_short_writes_short_artifacts(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    longdir = tmp_path / "produced" / "zz" / "long"
    longdir.mkdir(parents=True)
    (longdir / "script.md").write_text("# T\n\nIn 1984 Senna chased Prost at Monaco. Seven seconds.\n")
    monkeypatch.setattr(run_produce, "derive_short_tease",
                        lambda long_script, idea: {"script": "Senna chased Prost at Monaco in 1984.", "mood": "somber"})
    monkeypatch.setattr(run_produce, "generate_short_metadata",
                        lambda idea, s: {"title": "Senna Short", "description": "d", "tags": []})
    seen = {}
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: seen.update(f))
    idea = {"id": "zz", "title_variants": ["T"], "sport": "F1"}
    res = run_produce.produce_companion_short(idea)
    assert (tmp_path / "produced" / "zz" / "short" / "script.md").exists()
    assert (tmp_path / "produced" / "zz" / "short" / "metadata.json").exists()
    assert res["within_long"] is True
    assert seen.get("short_status") == "short_ready"
    assert seen.get("mood") == "somber"


def test_produce_companion_short_flags_when_guard_fails(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    longdir = tmp_path / "produced" / "zz" / "long"
    longdir.mkdir(parents=True)
    (longdir / "script.md").write_text("# T\n\nIn 1984 Senna chased Prost at Monaco.\n")
    monkeypatch.setattr(run_produce, "derive_short_tease",
                        lambda long_script, idea: {"script": "Senna beat Mansell by 1992 points.", "mood": "hype"})
    monkeypatch.setattr(run_produce, "generate_short_metadata",
                        lambda idea, s: {"title": "x", "description": "d", "tags": []})
    seen = {}
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: seen.update(f))
    res = run_produce.produce_companion_short({"id": "zz", "title_variants": ["T"], "sport": "F1"})
    assert res["within_long"] is False
    assert seen.get("short_status") == "short_needs_review"
