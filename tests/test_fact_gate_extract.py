from engine.pipeline import fact_gate


def test_extract_returns_claims_and_applies_recent_backstop(monkeypatch):
    fake = {"claims": [
        {"text": "Senna died at Imola in 1994", "entity": "Death of Ayrton Senna",
         "fact": "died at Imola 1994", "era": "encyclopedic"},
        {"text": "Iran is in Group G of the 2026 World Cup", "entity": "2026 FIFA World Cup",
         "fact": "Iran in Group G", "era": "encyclopedic"},  # model mis-tagged; heuristic must fix
    ]}
    monkeypatch.setattr(fact_gate, "_structured", lambda *a, **k: fake)
    monkeypatch.setattr(fact_gate.datetime, "date",
                        type("D", (), {"today": staticmethod(lambda: type("d", (), {"year": 2026})())}))
    claims = fact_gate.extract_and_classify("script", max_claims=25)
    assert claims[0]["era"] == "encyclopedic"
    assert claims[1]["era"] == "recent"            # backstop overrode the model tag
    assert all({"text", "entity", "fact", "era"} <= set(c) for c in claims)


def test_extract_respects_cap(monkeypatch):
    fake = {"claims": [{"text": f"c{i}", "entity": "e", "fact": "f", "era": "encyclopedic"}
                       for i in range(30)]}
    monkeypatch.setattr(fact_gate, "_structured", lambda *a, **k: fake)
    assert len(fact_gate.extract_and_classify("s", max_claims=25)) == 25
