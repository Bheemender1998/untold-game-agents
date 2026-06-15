import json
from engine import config
from engine import queue_manager as q
from engine.queue import json_backend


def _seed(tmp_path, monkeypatch, ideas):
    # Force the JSON backend: the queue dispatcher (engine/queue/__init__._active) routes to Neon
    # whenever config.DATABASE_URL is set, and config loads it from .env — so without this these
    # JSON-fixture tests query Neon and the seeded ideas are invisible (get_by_id → None).
    monkeypatch.setattr(config, "DATABASE_URL", None, raising=False)
    qf = tmp_path / "idea_queue.json"
    qf.write_text(json.dumps(ideas))
    monkeypatch.setattr(json_backend, "QUEUE_FILE", str(qf))
    return qf


def test_migration_moves_youtube_url_to_short(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "a", "status": "published", "youtube_url": "https://youtu.be/AAA"},
    ])
    moved = q.split_youtube_url_field()
    assert moved == 1
    idea = q.get_by_id("a")
    assert idea["short_youtube_url"] == "https://youtu.be/AAA"
    assert "youtube_url" not in q.get_by_id("a")


def test_skips_when_short_already_set(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "a", "youtube_url": "https://youtu.be/AAA",
         "short_youtube_url": "https://youtu.be/EXISTING"},
    ])
    moved = q.split_youtube_url_field()
    assert moved == 0
    assert q.get_by_id("a")["short_youtube_url"] == "https://youtu.be/EXISTING"
    assert "youtube_url" not in q.get_by_id("a")  # legacy key retired even when short already set


def test_skips_when_no_youtube_url(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "b", "status": "pending"},
    ])
    moved = q.split_youtube_url_field()
    assert moved == 0
    assert "short_youtube_url" not in q.get_by_id("b")
