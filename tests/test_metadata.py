from engine.pipeline import metadata


def test_generate_short_metadata_assembles_description(monkeypatch):
    monkeypatch.setattr(metadata, "_short_desc_llm",
                        lambda idea, script: ("A wet night in Monaco hid a scandal. One flag changed everything.",
                                              ["Senna", "Prost", "Monaco 1984"]))
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
    idea = {"title_variants": ["The Race That Was Stolen"], "sport": "F1",
            "pillar": "verdict_revisited"}
    m = metadata.generate_short_metadata(idea, "In the pouring rain of Monaco, 1984...")
    assert m["title"] == "The Race That Was Stolen"
    assert m["description"].startswith("A wet night in Monaco")
    assert "#Shorts #F1" in m["description"]
    assert "MOOD" not in m["description"] and "---" not in m["description"]
    assert m["tags"][0] == "Shorts" and "F1" in m["tags"] and "Senna" in m["tags"]
    assert len(m["tags"]) <= 30


def test_generate_short_metadata_falls_back_on_llm_error(monkeypatch):
    def boom(idea, script):
        raise RuntimeError("llm down")
    monkeypatch.setattr(metadata, "_short_desc_llm", boom)
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
    idea = {"title_variants": ["T"], "sport": "NFL", "pillar": "forgotten_figure"}
    m = metadata.generate_short_metadata(idea, "He walked away at his peak.\nMore text.")
    assert m["description"].startswith("He walked away at his peak.\n\n#Shorts #NFL")  # minimal fallback
    assert "Subscribe → @untoldgamemedia" in m["description"]
    assert m["tags"] == ["Shorts", "NFL", "forgotten_figure"]


def test_short_description_has_subscribe_cta(monkeypatch):
    from engine import config
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
    m = metadata.generate_short_metadata({"title_variants": ["T"], "sport": "F1", "pillar": "p"}, "Hook.")
    assert m["description"].rstrip().endswith(config.CHANNEL_HANDLE)
    assert "Subscribe" in m["description"]


def test_title_rule_present_in_metadata_system():
    from engine.pipeline import metadata
    assert "Open the gap by withholding" in metadata.METADATA_SYSTEM
    assert "exact verified values or none" in metadata.METADATA_SYSTEM


def test_short_title_pass_used_when_clean(monkeypatch):
    from engine.pipeline import metadata
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: "10 Days After This Own Goal, He Was Dead")
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Andres Escobar Story"], "sport": "Soccer", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "Ten days after the own goal, in 10 minutes...")
    assert m["title"] == "10 Days After This Own Goal, He Was Dead"


def test_short_title_falls_back_when_llm_errors(monkeypatch):
    from engine.pipeline import metadata
    def boom(idea, script):
        raise RuntimeError("llm down")
    monkeypatch.setattr(metadata, "_short_title_llm", boom)
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Long Poetic Title"], "sport": "F1", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "Some verified script.")
    assert m["title"] == "The Long Poetic Title"   # self-stub to title_variants[0]


def test_short_title_falls_back_when_backstop_rejects_fabricated_number(monkeypatch):
    from engine.pipeline import metadata
    # generated title invents '1500'; script only has '1457' -> backstop rejects -> fall back.
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: "1500 Yards From Immortality")
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Barry Sanders Story"], "sport": "NFL", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "He retired 1457 yards short of the record.")
    assert m["title"] == "The Barry Sanders Story"


def test_short_title_rule_present_in_short_title_system():
    from engine.pipeline import metadata
    assert "Open the gap by withholding" in metadata._SHORT_TITLE_SYSTEM
