from engine.pipeline import metadata


def test_generate_short_metadata_assembles_description(monkeypatch):
    monkeypatch.setattr(metadata, "_short_desc_llm",
                        lambda idea, script: ("A wet night in Monaco hid a scandal. One flag changed everything.",
                                              ["Senna", "Prost", "Monaco 1984"]))
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
    idea = {"title_variants": ["T"], "sport": "NFL", "pillar": "forgotten_figure"}
    m = metadata.generate_short_metadata(idea, "He walked away at his peak.\nMore text.")
    assert m["description"] == "He walked away at his peak.\n\n#Shorts #NFL"  # minimal fallback
    assert m["tags"] == ["Shorts", "NFL", "forgotten_figure"]
