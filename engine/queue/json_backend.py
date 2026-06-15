"""
JSON-file queue backend.
All I/O + mutation functions from the original queue_manager.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from engine.config import QUEUE_FILE, MIN_VIRAL_SCORE


# ── Queue I/O ─────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)


def _save(ideas: list[dict]) -> None:
    # Atomic write (temp file + os.replace) so the production record is never left
    # half-written — a crash mid-save can't corrupt idea_queue.json.
    d = os.path.dirname(QUEUE_FILE)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(ideas, f, indent=2)
        os.replace(tmp, QUEUE_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_idea(idea: dict) -> bool:
    """Add idea to queue. Returns False if below MIN_VIRAL_SCORE threshold."""
    if idea["scores"]["viral_overall"] < MIN_VIRAL_SCORE:
        print(f"  ✗ Filtered (score {idea['scores']['viral_overall']} < {MIN_VIRAL_SCORE}): {idea['title_variants'][0]}")
        return False
    ideas = _load()
    ideas.append(idea)
    _save(ideas)
    print(f"  ✓ Queued [{idea['id']}] score={idea['scores']['viral_overall']} — {idea['title_variants'][0]}")
    return True


def get_pending(min_score: Optional[float] = None) -> list[dict]:
    ideas = _load()
    filtered = [i for i in ideas if i["status"] == "pending"]
    if min_score:
        filtered = [i for i in filtered if i["scores"]["viral_overall"] >= min_score]
    return sorted(filtered, key=lambda x: x["scores"]["viral_overall"], reverse=True)


def approve(idea_id: str) -> bool:
    ideas = _load()
    for idea in ideas:
        if idea["id"] == idea_id:
            idea["status"] = "approved"
            idea["approved_at"] = datetime.now(timezone.utc).isoformat()
            _save(ideas)
            return True
    return False


def reject(idea_id: str, reason: str = "") -> bool:
    ideas = _load()
    for idea in ideas:
        if idea["id"] == idea_id:
            idea["status"] = "rejected"
            idea["rejection_reason"] = reason
            _save(ideas)
            return True
    return False


def mark_in_production(idea_id: str) -> bool:
    ideas = _load()
    for idea in ideas:
        if idea["id"] == idea_id:
            idea["status"] = "in_production"
            _save(ideas)
            return True
    return False


def get_by_status(status: str) -> list[dict]:
    """All ideas in a given status, highest viral score first."""
    return sorted(
        [i for i in _load() if i["status"] == status],
        key=lambda x: x["scores"]["viral_overall"], reverse=True,
    )


def get_by_id(idea_id: str) -> Optional[dict]:
    return next((i for i in _load() if i["id"] == idea_id), None)


def update_idea(idea_id: str, **fields) -> bool:
    """Merge arbitrary fields into an idea (e.g. script_path, metadata_path)."""
    ideas = _load()
    for idea in ideas:
        if idea["id"] == idea_id:
            idea.update(fields)
            _save(ideas)
            return True
    return False


def split_youtube_url_field() -> int:
    """One-time migration: move a legacy single `youtube_url` to `short_youtube_url`
    (the existing published uploads are all shorts). Idempotent. Always retires the
    legacy `youtube_url` key once `short_youtube_url` is set, so no stale field lingers.
    Returns the number of ideas migrated (not counting pure cleanups)."""
    ideas = _load()
    moved, dirty = 0, False
    for idea in ideas:
        if not idea.get("youtube_url"):
            continue
        if not idea.get("short_youtube_url"):
            idea["short_youtube_url"] = idea["youtube_url"]
            moved += 1
        del idea["youtube_url"]   # retire the legacy key once short is populated
        dirty = True
    if dirty:
        _save(ideas)
    return moved


def stats() -> dict:
    ideas = _load()
    statuses = {}
    for i in ideas:
        statuses[i["status"]] = statuses.get(i["status"], 0) + 1
    agents = {}
    for i in ideas:
        agents[i["source_agent"]] = agents.get(i["source_agent"], 0) + 1
    avg_score = (
        round(sum(i["scores"]["viral_overall"] for i in ideas) / len(ideas), 1)
        if ideas else 0
    )
    return {
        "total": len(ideas),
        "by_status": statuses,
        "by_agent": agents,
        "avg_viral_score": avg_score,
    }
