from engine.pipeline import fact_gate


_EXTRACT = ("Ayrton Senna was a Brazilian driver. He won three titles. "
            "On lap 7 his car entered Tamburello at 309 km/h and struck the wall at 211 km/h. "
            "Italian courts later ruled steering column failure.")


def test_window_pulls_the_sentence_with_the_fact():
    out = fact_gate._window(_EXTRACT, "struck the wall at 211 km/h")
    assert "211 km/h" in out
    assert "Brazilian driver" not in out          # irrelevant intro sentence excluded


def test_window_empty_when_fact_absent():
    assert fact_gate._window(_EXTRACT, "won the 1995 championship in Monaco") == ""


def test_window_capped(monkeypatch):
    big = " ".join(f"Sentence {i} about lap seven crash." for i in range(500))
    out = fact_gate._window(big, "lap seven crash", max_chars=400)
    assert len(out) <= 400
