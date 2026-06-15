"""One-time idempotent import of the local idea_queue.json into Neon.
Upserts by id, so re-running is safe. Requires DATABASE_URL to be set."""
import json
import sys
from engine.config import QUEUE_FILE
from engine.queue import neon_backend


def load_ideas(path: str = QUEUE_FILE) -> list:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def main():
    ideas = load_ideas()
    n = 0
    for idea in ideas:
        # bypass the score filter: migrate existing rows verbatim via upsert
        with neon_backend._conn() as c:
            c.execute(
                "INSERT INTO ideas (id,status,viral_score,source_agent,created_at,data) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET "
                "status=EXCLUDED.status, viral_score=EXCLUDED.viral_score, "
                "source_agent=EXCLUDED.source_agent, data=EXCLUDED.data",
                neon_backend._promoted(idea))
        n += 1
    print(f"migrated {n} ideas into Neon")
    return n


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
