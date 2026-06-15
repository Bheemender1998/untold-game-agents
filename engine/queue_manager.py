"""
Shared Idea Queue
─────────────────
Thread-safe JSON queue that all 4 agents write into.
Stores ideas, scores, metadata, and approval status.
"""

import uuid
from datetime import datetime, timezone


# ── Data model ────────────────────────────────────────────────────────────────

def new_idea(
    title_variants: list[str],
    hook: str,
    pillar: str,
    sport: str,
    target_audience: str,
    viral_score: float,
    curiosity_score: float,
    emotion_score: float,
    search_score: float,
    share_score: float,
    evergreen_score: float,
    seo_keywords: list[str],
    why_it_works: str,
    source_agent: str,
    thumbnail_concept: str = "",
    format_suggestion: str = "Long form 12-18 min",
) -> dict:
    return {
        "id": str(uuid.uuid4())[:8],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",           # pending | approved | rejected | in_production
        "source_agent": source_agent,
        "title_variants": title_variants,
        "hook": hook,
        "pillar": pillar,
        "sport": sport,
        "target_audience": target_audience,
        "format_suggestion": format_suggestion,
        "thumbnail_concept": thumbnail_concept,
        "seo_keywords": seo_keywords,
        "why_it_works": why_it_works,
        "scores": {
            "viral_overall": round(viral_score, 1),
            "curiosity":     round(curiosity_score, 1),
            "emotion":       round(emotion_score, 1),
            "search":        round(search_score, 1),
            "shareability":  round(share_score, 1),
            "evergreen":     round(evergreen_score, 1),
        },
    }


# Backend-dispatched I/O (JSON file or Neon). Importing from engine.queue_manager
# stays valid for every existing caller.
from engine.queue import (  # noqa: E402
    add_idea, get_pending, approve, reject, mark_in_production,
    get_by_status, get_by_id, update_idea, stats, split_youtube_url_field,
)
