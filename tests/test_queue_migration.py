import json
from engine import queue_manager as q


def _seed(tmp_path, monkeypatch, ideas):
    qf = tmp_path / "idea_queue.json"
    qf.write_text(json.dumps(ideas))
    monkeypatch.setattr(q, "QUEUE_FILE", str(qf))
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
