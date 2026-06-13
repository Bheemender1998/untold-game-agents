from engine import run_produce


def test_shadow_routes_passed_script_to_needs_review(tmp_path, monkeypatch):
    monkeypatch.setattr(run_produce, "_atomic_write", lambda *a, **k: None)
    monkeypatch.setattr(run_produce.os.path, "exists", lambda p: False)
    monkeypatch.setattr(run_produce.os, "makedirs", lambda *a, **k: None)
    import engine.pipeline.factcheck as fc
    monkeypatch.setattr(fc, "factcheck", lambda *a, **k: {
        "passed": True, "would_auto_pass": True, "issues": [], "checked": 2, "complete": True})
    monkeypatch.setattr(run_produce.config, "FACT_GATE_SHADOW", True)
    shadow_lines = []
    monkeypatch.setattr(run_produce, "_append_shadow", lambda rec: shadow_lines.append(rec))
    monkeypatch.setattr(run_produce, "generate_script", lambda idea: "Long script body.")
    monkeypatch.setattr(run_produce, "generate_metadata", lambda *a, **k: {"title": "T"})
    updates = []
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: updates.append(f))
    idea = {"id": "x", "title_variants": ["T"], "script": "Body.",
            "pillar": "hidden_story", "sport": "F1"}

    run_produce.produce(idea, fmt="long")
    assert updates[-1]["status"] == "needs_review"
    assert shadow_lines and shadow_lines[0]["would_auto_pass"] is True


def test_live_mode_passed_script_goes_in_production(tmp_path, monkeypatch):
    monkeypatch.setattr(run_produce, "_atomic_write", lambda *a, **k: None)
    monkeypatch.setattr(run_produce.os.path, "exists", lambda p: False)
    monkeypatch.setattr(run_produce.os, "makedirs", lambda *a, **k: None)
    import engine.pipeline.factcheck as fc
    monkeypatch.setattr(fc, "factcheck", lambda *a, **k: {
        "passed": True, "would_auto_pass": True, "issues": [], "checked": 2, "complete": True})
    monkeypatch.setattr(run_produce.config, "FACT_GATE_SHADOW", False)
    monkeypatch.setattr(run_produce, "_append_shadow", lambda rec: None)
    monkeypatch.setattr(run_produce, "generate_script", lambda idea: "Long script body.")
    monkeypatch.setattr(run_produce, "generate_metadata", lambda *a, **k: {"title": "T"})
    updates = []
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: updates.append(f))
    idea = {"id": "x", "title_variants": ["T"], "script": "Body.", "pillar": "hidden_story", "sport": "F1"}

    run_produce.produce(idea, fmt="long")
    assert updates[-1]["status"] == "in_production"
