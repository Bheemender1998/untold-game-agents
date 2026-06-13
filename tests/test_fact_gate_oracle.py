from engine.pipeline import fact_gate


# ── (A) Oracle: the three known-wrong claims must be flagged, the right ones supported ──
# Fixtures encode the 2026-06-13 hand-review verdicts at claim granularity. Evidence is the
# authoritative Wikipedia text fetched during that review.
_WRONG = [
    ({"text": "Alexi Lalas played in the 1998 Iran-USA match", "entity": "1998 FIFA World Cup Group F",
      "fact": "Lalas played", "era": "encyclopedic"},
     {"kind": "encyclopedic", "source": "Wikipedia: 1998 FIFA World Cup Group F",
      "text": "United States XI: Keller, Hejduk, Burns, Dooley, Regis, Ramos, Reyna, Moore, Jones, Wegerle, McBride."}),
    ({"text": "Pat Symonds was Renault's technical director in 2008", "entity": "Renault Formula One crash controversy",
      "fact": "Symonds technical director", "era": "encyclopedic"},
     {"kind": "encyclopedic", "source": "Wikipedia: Renault Formula One crash controversy",
      "text": "Pat Symonds, its executive director of engineering, ..."}),
    ({"text": "Briatore returned to F1 in 2022 as an ambassador", "entity": "Flavio Briatore",
      "fact": "returned 2022 ambassador", "era": "encyclopedic"},
     {"kind": "encyclopedic", "source": "Wikipedia: Flavio Briatore",
      "text": "Briatore returned to Formula One in June 2024 as executive advisor to Alpine."}),
]
_RIGHT = [
    ({"text": "Piquet crashed on lap 15 at Turn 17", "entity": "Renault Formula One crash controversy",
      "fact": "lap 15 turn 17", "era": "encyclopedic"},
     {"kind": "encyclopedic", "source": "Wikipedia: Renault Formula One crash controversy",
      "text": "On the 15th lap the Renault driven by Piquet crashed into the wall at turn seventeen."}),
    ({"text": "Mahdavikia scored in the 84th minute", "entity": "1998 FIFA World Cup Group F",
      "fact": "Mahdavikia 84th minute", "era": "encyclopedic"},
     {"kind": "encyclopedic", "source": "Wikipedia: 1998 FIFA World Cup Group F",
      "text": "Mahdavikia scored at 84' to make it 2-0."}),
]


def test_oracle_flags_known_errors_and_supports_correct():
    """Real judge call (no mock) — skips without an API key so offline CI can run."""
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        import pytest; pytest.skip("needs ANTHROPIC_API_KEY (live judge call)")
    wrong = fact_gate.judge(_WRONG)
    assert all(v["verdict"] != "supported" for v in wrong), wrong   # never false-pass an error
    right = fact_gate.judge(_RIGHT)
    assert all(v["verdict"] == "supported" for v in right), right


# ── (B) Stage 1-2 resolution: real gather_evidence vs recorded MediaWiki responses ──
def test_resolution_lands_on_right_page_and_windows_deep_fact(monkeypatch):
    monkeypatch.setattr(fact_gate.wikipedia, "search_title",
                        lambda q: "1998 FIFA World Cup Group F")
    monkeypatch.setattr(fact_gate.wikipedia, "extract", lambda t: (
        "Group F featured the USA and Iran. "  # intro — does NOT contain the minute
        "Estili scored at 40'. Mahdavikia scored at 84' to make it 2-0. McBride replied at 87'."))
    monkeypatch.setattr(fact_gate, "web_search",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not hit DDG")))
    ev = fact_gate.gather_evidence(
        {"text": "Mahdavikia scored in the 84th minute", "entity": "1998 FIFA World Cup Group F",
         "fact": "Mahdavikia 84th minute", "era": "encyclopedic"}, {"resolutions": {}, "extracts": {}})
    assert ev["kind"] == "encyclopedic"
    assert "84'" in ev["text"]                       # deep fact reached evidence (not intro-only)
