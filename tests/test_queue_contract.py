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
