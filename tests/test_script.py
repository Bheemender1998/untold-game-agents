from engine.pipeline import script


def test_generate_short_script_returns_script_and_mood(monkeypatch):
    fake = ("MOOD: tense\n"
            "The own goal that cost him his life. In 1994, Andres Escobar scored "
            "into his own net at the World Cup. Ten days later he was shot dead in a "
            "Medellin parking lot. The game never forgot him.")
    monkeypatch.setattr(script.ShortScriptWriter, "_call", lambda self, p, **k: fake)
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "sport_vs_world", "sport": "Soccer",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == "tense"
    assert "MOOD:" not in out["script"]          # mood line stripped from spoken script
    assert out["script"].startswith("The own goal")
    assert len(out["script"].split()) >= 10


def test_generate_short_script_defaults_mood_when_absent(monkeypatch):
    monkeypatch.setattr(script.ShortScriptWriter, "_call",
                        lambda self, p, **k: "Just narration, no mood line here.")
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "hidden_story", "sport": "NFL",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == ""                      # absent → empty (caller falls back to pillar)
    assert "Just narration" in out["script"]


def test_short_mood_only_accepts_known_values(monkeypatch):
    monkeypatch.setattr(script.ShortScriptWriter, "_call",
                        lambda self, p, **k: "MOOD: banana\nSome narration text.")
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "what_if", "sport": "F1",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == ""                      # unknown mood rejected → empty
    assert "Some narration text" in out["script"]


def test_short_mood_line_with_empty_body_does_not_leak(monkeypatch):
    monkeypatch.setattr(script.ShortScriptWriter, "_call",
                        lambda self, p, **k: "MOOD: triumphant\n")
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "what_if", "sport": "F1",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == "triumphant"
    assert "MOOD" not in out["script"]       # the mood line must never leak into the spoken text


def test_short_mid_script_mood_line_is_not_a_header(monkeypatch):
    monkeypatch.setattr(script.ShortScriptWriter, "_call",
                        lambda self, p, **k: "The real hook line.\nMOOD: looks like a header but is narration.")
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "what_if", "sport": "F1",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == ""                              # no leading MOOD → none parsed
    assert out["script"].startswith("The real hook line.")
    assert "MOOD: looks like a header" in out["script"]   # mid-text line stays as narration


def test_short_tolerates_leading_markdown_rule_before_mood(monkeypatch):
    # Models often wrap output in a '---' rule before the MOOD line — that must not defeat
    # the parse (regression: a leaked 'MOOD:' line would otherwise be spoken by TTS).
    raw = "---\n\nMOOD: tense\n\nThe Knicks last won a title in 1973."
    monkeypatch.setattr(script.ShortScriptWriter, "_call", lambda self, p, **k: raw)
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "sport_vs_world", "sport": "NBA",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == "tense"
    assert out["script"] == "The Knicks last won a title in 1973."
    assert "MOOD" not in out["script"]
    assert "---" not in out["script"]


def test_short_strips_leading_rule_even_without_mood(monkeypatch):
    # Same '---' wrapper failure mode, but the model omitted MOOD entirely: the rule must
    # still not leak into the spoken script; mood falls back to '' (caller uses the pillar).
    monkeypatch.setattr(script.ShortScriptWriter, "_call",
                        lambda self, p, **k: "---\n\nThe real narration starts here.")
    out = script.generate_short_script({"title_variants": ["X"], "hook": "h",
                                        "pillar": "what_if", "sport": "F1",
                                        "target_audience": "fans", "why_it_works": "w"})
    assert out["mood"] == ""
    assert out["script"] == "The real narration starts here."
    assert "---" not in out["script"]
