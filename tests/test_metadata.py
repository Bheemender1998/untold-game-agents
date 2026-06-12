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
    assert m["description"].startswith("He walked away at his peak.\n\n#Shorts #NFL")  # minimal fallback
    assert "Subscribe → @untoldgamemedia" in m["description"]
    assert m["tags"] == ["Shorts", "NFL", "forgotten_figure"]


def test_short_description_has_subscribe_cta(monkeypatch):
    from engine import config
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    m = metadata.generate_short_metadata({"title_variants": ["T"], "sport": "F1", "pillar": "p"}, "Hook.")
    assert m["description"].rstrip().endswith(config.CHANNEL_HANDLE)
    assert "Subscribe" in m["description"]
