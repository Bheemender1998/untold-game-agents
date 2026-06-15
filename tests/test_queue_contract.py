from engine import config
from engine import queue as q
from engine.queue import json_backend


def test_selector_defaults_to_json(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", None)
    assert q._active() is json_backend


def test_selector_picks_neon_when_db_url_set(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgres://example/db")
    from engine.queue import neon_backend
    assert q._active() is neon_backend


from pathlib import Path

def test_schema_defines_ideas_and_costs():
    sql = Path("engine/db/schema_queue.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS ideas" in sql
    assert "data         JSONB" in sql or "data JSONB" in sql
    assert "CREATE TABLE IF NOT EXISTS api_costs" in sql


# ── Parametrized backend contract ─────────────────────────────────────────────

import os, json, uuid
import pytest
from engine.queue import json_backend


def _sample_idea(score=8.0):
    iid = str(uuid.uuid4())[:8]
    return {
        "id": iid, "created_at": "2026-06-14T00:00:00+00:00", "status": "pending",
        "source_agent": "evergreen_agent", "title_variants": ["T"], "hook": "h",
        "pillar": "what_if", "sport": "F1", "target_audience": "fans",
        "format_suggestion": "Long form 8-9 min", "thumbnail_concept": "",
        "seo_keywords": ["k"], "why_it_works": "w",
        "scores": {"viral_overall": score, "curiosity": score, "emotion": score,
                   "search": score, "shareability": score, "evergreen": score},
    }


def _backends():
    backends = [("json", json_backend)]
    if os.environ.get("TEST_DATABASE_URL"):
        from engine.queue import neon_backend
        backends.append(("neon", neon_backend))
    return backends


@pytest.fixture(params=_backends(), ids=lambda b: b[0])
def backend(request, tmp_path, monkeypatch):
    name, mod = request.param
    if name == "json":
        monkeypatch.setattr(json_backend, "QUEUE_FILE", str(tmp_path / "q.json"))
    else:
        monkeypatch.setattr(config, "DATABASE_URL", os.environ["TEST_DATABASE_URL"])
        monkeypatch.setattr(mod, "DATABASE_URL", os.environ["TEST_DATABASE_URL"])
        with mod._conn() as c:                       # clean slate per test
            c.execute("TRUNCATE ideas")
    return mod


def test_add_get_pending_roundtrip(backend):
    idea = _sample_idea()
    assert backend.add_idea(idea) is True
    pending = backend.get_pending()
    assert any(i["id"] == idea["id"] for i in pending)


def test_below_threshold_filtered(backend):
    assert backend.add_idea(_sample_idea(score=1.0)) is False
    assert backend.get_pending() == []


def test_pending_sorted_by_score_desc(backend):
    lo, hi = _sample_idea(7.0), _sample_idea(9.0)
    backend.add_idea(lo); backend.add_idea(hi)
    scores = [i["scores"]["viral_overall"] for i in backend.get_pending()]
    assert scores == sorted(scores, reverse=True)


def test_approve_and_status_query(backend):
    idea = _sample_idea(); backend.add_idea(idea)
    assert backend.approve(idea["id"]) is True
    assert backend.get_pending() == []
    assert any(i["id"] == idea["id"] for i in backend.get_by_status("approved"))


def test_update_idea_merges_arbitrary_fields(backend):
    idea = _sample_idea(); backend.add_idea(idea)
    assert backend.update_idea(idea["id"], long_youtube_url="https://youtu.be/x") is True
    got = backend.get_by_id(idea["id"])
    assert got["long_youtube_url"] == "https://youtu.be/x"
