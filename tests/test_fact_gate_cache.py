import json, time
from engine.pipeline import fact_gate


def test_cache_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / ".factcache.json"
    monkeypatch.setattr(fact_gate.config, "FACTCACHE_PATH", str(p))
    cache = {"resolutions": {"q": "T"}, "extracts": {"T": {"text": "x", "fetched_at": time.time()}}}
    fact_gate._cache_save(cache)
    assert fact_gate._cache_load() == cache


def test_cache_load_missing_returns_empty_skeleton(tmp_path, monkeypatch):
    monkeypatch.setattr(fact_gate.config, "FACTCACHE_PATH", str(tmp_path / "nope.json"))
    assert fact_gate._cache_load() == {"resolutions": {}, "extracts": {}}


def test_cache_load_corrupt_returns_skeleton(tmp_path, monkeypatch):
    p = tmp_path / ".factcache.json"; p.write_text("{not json")
    monkeypatch.setattr(fact_gate.config, "FACTCACHE_PATH", str(p))
    assert fact_gate._cache_load() == {"resolutions": {}, "extracts": {}}


def test_extract_fresh_vs_stale(monkeypatch):
    monkeypatch.setattr(fact_gate.config, "FACTCACHE_TTL_DAYS", 30)
    now = 1_000_000.0
    monkeypatch.setattr(fact_gate.time, "time", lambda: now)
    fresh = {"text": "x", "fetched_at": now - 10 * 86400}
    stale = {"text": "x", "fetched_at": now - 40 * 86400}
    assert fact_gate._fresh(fresh) is True
    assert fact_gate._fresh(stale) is False
