from engine.pipeline import fact_gate


def test_future_or_current_year_forces_recent(monkeypatch):
    monkeypatch.setattr(fact_gate.datetime, "date",
                        type("D", (), {"today": staticmethod(lambda: type("d", (), {"year": 2026})())}))
    assert fact_gate._force_recent("Iran is in Group G of the 2026 World Cup") is True
    assert fact_gate._force_recent("A ruling on November 20, 2027") is True


def test_temporal_phrases_force_recent(monkeypatch):
    monkeypatch.setattr(fact_gate.datetime, "date",
                        type("D", (), {"today": staticmethod(lambda: type("d", (), {"year": 2026})())}))
    for s in ["currently the champion", "as of this year", "last week he signed", "this season"]:
        assert fact_gate._force_recent(s) is True


def test_old_historical_claim_not_forced(monkeypatch):
    monkeypatch.setattr(fact_gate.datetime, "date",
                        type("D", (), {"today": staticmethod(lambda: type("d", (), {"year": 2026})())}))
    assert fact_gate._force_recent("Senna died at Imola in 1994") is False
    assert fact_gate._force_recent("Massa won six races in 2008") is False
