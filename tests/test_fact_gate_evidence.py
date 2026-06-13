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
