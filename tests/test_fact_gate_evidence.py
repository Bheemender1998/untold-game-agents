import time
from engine.pipeline import fact_gate


def _claim(era="encyclopedic"):
    return {"text": "Mahdavikia scored in the 84th minute", "entity": "1998 FIFA World Cup Group F",
            "fact": "Mahdavikia 84th minute", "era": era}


def test_encyclopedic_uses_mediawiki_no_ddg(monkeypatch):
    monkeypatch.setattr(fact_gate.wikipedia, "search_title", lambda q: "1998 FIFA World Cup Group F")
    monkeypatch.setattr(fact_gate.wikipedia, "extract",
                        lambda t: "Estili scored. Mahdavikia scored in the 84th minute. USA replied.")
    called = {"ddg": False}
    monkeypatch.setattr(fact_gate, "web_search", lambda *a, **k: called.__setitem__("ddg", True) or "x")
    cache = {"resolutions": {}, "extracts": {}}
    ev = fact_gate.gather_evidence(_claim(), cache)
    assert ev["kind"] == "encyclopedic" and "84th minute" in ev["text"]
    assert called["ddg"] is False
    assert cache["extracts"]["1998 FIFA World Cup Group F"]["text"]


def test_title_resolves_on_entity_not_fact(monkeypatch):
    # Regression: appending the fact sentence to the search query pollutes MediaWiki's
    # full-text search and resolves the wrong (often current-era) article. The title must
    # be resolved on the entity ALONE -- the fact is only for windowing the extract.
    # The fake reproduces the real failure: a polluted query (entity + fact words) ranks
    # the wrong current-era article; the bare entity resolves correctly.
    EXTRACTS = {
        "1973 NBA Finals": "The New York Knicks defeated the Los Angeles Lakers 4-1.",
        "2026 NBA Finals": "The 2026 NBA Finals were contested in June 2026.",
    }
    def fake_search_title(q):
        return "2026 NBA Finals" if "five games" in q else "1973 NBA Finals"
    monkeypatch.setattr(fact_gate.wikipedia, "search_title", fake_search_title)
    monkeypatch.setattr(fact_gate.wikipedia, "extract", lambda t: EXTRACTS.get(t, ""))
    monkeypatch.setattr(fact_gate, "web_search", lambda *a, **k: "x")
    claim = {"text": "Knicks beat Lakers in the 1973 Finals", "entity": "1973 NBA Finals",
             "fact": "Knicks defeated Lakers in five games", "era": "encyclopedic"}
    ev = fact_gate.gather_evidence(claim, {"resolutions": {}, "extracts": {}})
    # entity-only resolution must reach the correct article, not the polluted 2026 one
    assert ev["source"] == "Wikipedia: 1973 NBA Finals"
    assert "defeated the Los Angeles Lakers" in ev["text"]


def test_encyclopedic_thin_falls_back_to_ddg(monkeypatch):
    monkeypatch.setattr(fact_gate.wikipedia, "search_title", lambda q: "Some Page")
    monkeypatch.setattr(fact_gate.wikipedia, "extract", lambda t: "Unrelated intro text only.")
    monkeypatch.setattr(fact_gate, "web_search", lambda *a, **k: "Search results for: x\n1. ...")
    ev = fact_gate.gather_evidence(_claim(), {"resolutions": {}, "extracts": {}})
    assert ev["kind"] == "web"


def test_recent_skips_mediawiki(monkeypatch):
    monkeypatch.setattr(fact_gate.wikipedia, "search_title",
                        lambda q: (_ for _ in ()).throw(AssertionError("should not resolve")))
    monkeypatch.setattr(fact_gate, "web_search", lambda *a, **k: "Search results for: x\n1. ...")
    ev = fact_gate.gather_evidence(_claim(era="recent"), {"resolutions": {}, "extracts": {}})
    assert ev["kind"] == "web"


def test_no_evidence_returns_none(monkeypatch):
    monkeypatch.setattr(fact_gate.wikipedia, "search_title", lambda q: None)
    monkeypatch.setattr(fact_gate, "web_search", lambda *a, **k: "[no web results for 'x']")
    ev = fact_gate.gather_evidence(_claim(), {"resolutions": {}, "extracts": {}})
    assert ev["kind"] == "none"


def test_extract_cache_hit_skips_refetch(monkeypatch):
    calls = {"n": 0}
    def fake_extract(t): calls["n"] += 1; return "Mahdavikia scored in the 84th minute."
    monkeypatch.setattr(fact_gate.wikipedia, "search_title", lambda q: "T")
    monkeypatch.setattr(fact_gate.wikipedia, "extract", fake_extract)
    cache = {"resolutions": {}, "extracts": {}}
    fact_gate.gather_evidence(_claim(), cache)
    fact_gate.gather_evidence(_claim(), cache)
    assert calls["n"] == 1
