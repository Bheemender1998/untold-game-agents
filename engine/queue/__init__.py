"""Queue backend selector. Neon when DATABASE_URL is set, else the JSON file.
Public functions match the historical queue_manager surface so no caller changes."""
from engine import config
from engine.queue import json_backend


def _active():
    """Resolve the active backend each call (cheap; lets tests flip DATABASE_URL)."""
    if getattr(config, "DATABASE_URL", None):
        from engine.queue import neon_backend  # imported lazily; no connect at import
        return neon_backend
    return json_backend


def add_idea(idea):                 return _active().add_idea(idea)
def get_pending(min_score=None):    return _active().get_pending(min_score)
def approve(idea_id):               return _active().approve(idea_id)
def reject(idea_id, reason=""):     return _active().reject(idea_id, reason)
def mark_in_production(idea_id):    return _active().mark_in_production(idea_id)
def get_by_status(status):          return _active().get_by_status(status)
def get_by_id(idea_id):             return _active().get_by_id(idea_id)
def update_idea(idea_id, **fields): return _active().update_idea(idea_id, **fields)
def stats():                        return _active().stats()
def split_youtube_url_field():      return _active().split_youtube_url_field()
