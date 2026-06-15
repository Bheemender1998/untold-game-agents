"""Neon Postgres backend for the idea queue (JSONB-document rows).
Mirrors json_backend. No connection is opened at import time."""
import psycopg
from psycopg.types.json import Jsonb
from datetime import datetime, timezone
from engine.config import DATABASE_URL, MIN_VIRAL_SCORE


def _conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)


def _promoted(idea):
    return (idea["id"], idea.get("status", "pending"),
            idea["scores"]["viral_overall"], idea.get("source_agent"),
            idea["created_at"], Jsonb(idea))


def add_idea(idea) -> bool:
    if idea["scores"]["viral_overall"] < MIN_VIRAL_SCORE:
        print(f"  ✗ Filtered (score {idea['scores']['viral_overall']} < {MIN_VIRAL_SCORE}): {idea['title_variants'][0]}")
        return False
    with _conn() as c:
        c.execute(
            "INSERT INTO ideas (id,status,viral_score,source_agent,created_at,data) "
            "VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, "
            "viral_score=EXCLUDED.viral_score, source_agent=EXCLUDED.source_agent, "
            "data=EXCLUDED.data", _promoted(idea))
    print(f"  ✓ Queued [{idea['id']}] score={idea['scores']['viral_overall']} — {idea['title_variants'][0]}")
    return True


def get_pending(min_score=None):
    sql = "SELECT data FROM ideas WHERE status='pending'"
    params = []
    if min_score is not None:
        sql += " AND viral_score >= %s"; params.append(min_score)
    sql += " ORDER BY viral_score DESC"
    with _conn() as c:
        return [r[0] for r in c.execute(sql, params).fetchall()]


def get_by_status(status):
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT data FROM ideas WHERE status=%s ORDER BY viral_score DESC",
            (status,)).fetchall()]


def get_by_id(idea_id):
    with _conn() as c:
        row = c.execute("SELECT data FROM ideas WHERE id=%s", (idea_id,)).fetchone()
    return row[0] if row else None


def _set_status(idea_id, status, **extra) -> bool:
    idea = get_by_id(idea_id)
    if idea is None:
        return False
    idea["status"] = status
    idea.update(extra)
    with _conn() as c:
        c.execute("UPDATE ideas SET status=%s, data=%s WHERE id=%s",
                  (status, Jsonb(idea), idea_id))
    return True


def approve(idea_id):
    return _set_status(idea_id, "approved",
                       approved_at=datetime.now(timezone.utc).isoformat())


def reject(idea_id, reason=""):
    return _set_status(idea_id, "rejected", rejection_reason=reason)


def mark_in_production(idea_id):
    return _set_status(idea_id, "in_production")


def update_idea(idea_id, **fields) -> bool:
    idea = get_by_id(idea_id)
    if idea is None:
        return False
    idea.update(fields)
    with _conn() as c:
        c.execute("UPDATE ideas SET data=%s, status=%s, viral_score=%s WHERE id=%s",
                  (Jsonb(idea), idea.get("status", "pending"),
                   idea["scores"]["viral_overall"], idea_id))
    return True


def split_youtube_url_field() -> int:
    """JSON-era migration; no-op on Neon (ideas are imported already-split)."""
    return 0


def stats() -> dict:
    with _conn() as c:
        rows = [r[0] for r in c.execute("SELECT data FROM ideas").fetchall()]
    statuses, agents = {}, {}
    for i in rows:
        statuses[i["status"]] = statuses.get(i["status"], 0) + 1
        agents[i["source_agent"]] = agents.get(i["source_agent"], 0) + 1
    avg = round(sum(i["scores"]["viral_overall"] for i in rows) / len(rows), 1) if rows else 0
    return {"total": len(rows), "by_status": statuses, "by_agent": agents, "avg_viral_score": avg}
