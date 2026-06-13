from engine.pipeline import fact_gate


def _wire(monkeypatch, claims, verdicts, tmp_path):
    monkeypatch.setattr(fact_gate.config, "FACTCACHE_PATH", str(tmp_path / ".fc.json"))
    monkeypatch.setattr(fact_gate, "extract_and_classify", lambda *a, **k: claims)
    monkeypatch.setattr(fact_gate, "gather_evidence",
                        lambda c, cache: {"kind": "encyclopedic", "text": "e", "source": "s"})
    monkeypatch.setattr(fact_gate, "judge", lambda items: verdicts)


def _claim(t): return {"text": t, "entity": "e", "fact": "f", "era": "encyclopedic"}
def _v(t, s): return {"claim": t, "verdict": s, "correction": "", "source": "", "evidence_kind": "encyclopedic"}


def test_all_supported_and_complete_passes(monkeypatch, tmp_path):
    claims = [_claim("a"), _claim("b")]
    _wire(monkeypatch, claims, [_v("a", "supported"), _v("b", "supported")], tmp_path)
    r = fact_gate.factcheck("script", max_claims=25)
    assert r["passed"] is True and r["would_auto_pass"] is True
    assert r["checked"] == 2 and r["supported"] == 2 and r["issues"] == []
    assert r["complete"] is True
    assert set(r) == {"checked", "supported", "issues", "complete", "max_claims", "passed", "would_auto_pass"}


def test_unverified_is_an_issue_not_dropped(monkeypatch, tmp_path):
    claims = [_claim("a"), _claim("b")]
    _wire(monkeypatch, claims, [_v("a", "supported"), _v("b", "unverified")], tmp_path)
    r = fact_gate.factcheck("script", max_claims=25)
    assert r["passed"] is False
    assert len(r["issues"]) == 1 and r["issues"][0]["verdict"] == "unverified"


def test_extraction_at_cap_marks_incomplete(monkeypatch, tmp_path):
    claims = [_claim(str(i)) for i in range(25)]
    _wire(monkeypatch, claims, [_v(str(i), "supported") for i in range(25)], tmp_path)
    r = fact_gate.factcheck("script", max_claims=25)
    assert r["complete"] is False and r["passed"] is False


def test_issue_carries_legacy_keys(monkeypatch, tmp_path):
    claims = [_claim("a")]
    v = {"claim": "a", "verdict": "contradicted", "correction": "fixed", "source": "Wikipedia: X",
         "evidence_kind": "encyclopedic"}
    _wire(monkeypatch, claims, [v], tmp_path)
    r = fact_gate.factcheck("s", max_claims=25)
    iss = r["issues"][0]
    assert iss["claim"] == "a" and iss["correction"] == "fixed" and iss["source"] == "Wikipedia: X"
