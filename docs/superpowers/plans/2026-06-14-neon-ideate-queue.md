# Neon-backed Idea Queue + Railway Ideate Cron — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the idea queue behind a pluggable backend so a Railway cron can stock a shared Neon Postgres queue every 2-3 days while the local machine reads/writes the same store; render stays local.

**Architecture:** `queue_manager`'s public functions become a thin dispatcher over two backends — `json_backend` (today's file impl, the offline/test fallback) and `neon_backend` (Postgres, JSONB-document rows). The backend is Neon when `DATABASE_URL` is set, else JSON. A `run_cron` entrypoint runs all 4 ideate agents under a per-run + rolling-30-day cost guard backed by a durable Neon `api_costs` ledger.

**Tech Stack:** Python 3 (main env), `psycopg` (v3) for Postgres/JSONB, Neon serverless Postgres, Railway cron, existing `engine/usage.py` cost ledger.

**Spec:** `docs/superpowers/specs/2026-06-14-neon-ideate-queue-design.md`

**Ship note:** this touches the live pipeline → after the plan is implemented, ship via the `ship-video-change` rail (dual adversarial review + `pytest tests/ -q`). Branch is already `feat/neon-ideate-queue`.

---

## File structure

| File | Responsibility |
|------|----------------|
| `engine/queue/__init__.py` | Backend selector + dispatch wrappers (public surface) |
| `engine/queue/json_backend.py` | Current JSON-file impl, moved verbatim |
| `engine/queue/neon_backend.py` | Postgres/JSONB impl of the same contract |
| `engine/queue_manager.py` | Keeps pure `new_idea()`; re-exports dispatched funcs (back-compat import path) |
| `engine/db/schema_queue.sql` | `ideas` + `api_costs` table DDL |
| `engine/db/migrate_queue.py` | One-time idempotent `idea_queue.json` → Neon import |
| `engine/cron_guard.py` | Pure cost-guard math + `monthly_spent_usd()` query |
| `engine/run_cron.py` | Cron entrypoint: guard → 4 agents → per-run cap |
| `engine/usage.py` | Extend `record()` to also write `api_costs` when `DATABASE_URL` set |
| `engine/config.py` | `DATABASE_URL`, `CRON_PER_RUN_CAP_USD`, `CRON_MONTHLY_CAP_USD` |
| `tests/test_queue_contract.py` | Backend contract tests (JSON always; Neon when `TEST_DATABASE_URL`) |
| `tests/test_cron_guard.py` | Guard math + run_cron orchestration (mocked) |
| `tests/test_queue_migration.py` | **Modify**: repoint monkeypatch to `json_backend` |
| `docs/adr/0006-neon-queue-railway-cron.md` | Decision record |
| `CLAUDE.md` | Deploy section update |

---

## Task 1: Extract queue backends (no behavior change)

**Files:**
- Create: `engine/queue/__init__.py`
- Create: `engine/queue/json_backend.py`
- Modify: `engine/queue_manager.py` (slim to `new_idea` + re-exports)
- Modify: `tests/test_queue_migration.py` (repoint monkeypatch)

- [ ] **Step 1: Move the JSON impl into `engine/queue/json_backend.py`**

Create `engine/queue/json_backend.py` with the I/O + mutation functions copied verbatim from the current `engine/queue_manager.py` (everything EXCEPT `new_idea`): `_load`, `_save`, `add_idea`, `get_pending`, `approve`, `reject`, `mark_in_production`, `get_by_status`, `get_by_id`, `update_idea`, `split_youtube_url_field`, `stats`. Keep the imports `from engine.config import QUEUE_FILE, MIN_VIRAL_SCORE` and `from datetime import datetime, timezone`. Do not change any logic.

- [ ] **Step 2: Create the dispatcher `engine/queue/__init__.py`**

```python
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
```

- [ ] **Step 3: Slim `engine/queue_manager.py` to the pure constructor + re-exports**

Replace the file body below the module docstring + `new_idea` definition with re-exports. Keep `new_idea` exactly as-is (pure, no I/O). Append:

```python
# Backend-dispatched I/O (JSON file or Neon). Importing from engine.queue_manager
# stays valid for every existing caller.
from engine.queue import (  # noqa: E402
    add_idea, get_pending, approve, reject, mark_in_production,
    get_by_status, get_by_id, update_idea, stats, split_youtube_url_field,
)
```

Delete the old `_load`, `_save`, and the mutation functions from `queue_manager.py` (they now live in `json_backend`).

- [ ] **Step 4: Repoint the migration test's monkeypatch**

In `tests/test_queue_migration.py`, the helper patches `q.QUEUE_FILE` where `q = engine.queue_manager`. That attribute no longer drives I/O. Change the import and patch target:

```python
from engine.queue import json_backend

def _seed(tmp_path, monkeypatch, ideas):
    qf = tmp_path / "idea_queue.json"
    qf.write_text(json.dumps(ideas))
    monkeypatch.setattr(json_backend, "QUEUE_FILE", str(qf))
```

Keep the test bodies calling `q.split_youtube_url_field()` (re-exported, dispatches to `json_backend`, which now reads the patched `QUEUE_FILE`).

- [ ] **Step 5: Run the full suite — must be green and unchanged**

Run: `python3 -m pytest tests/ -q`
Expected: PASS, same count as before the refactor (no behavior change).

- [ ] **Step 6: Commit**

```bash
git add engine/queue/ engine/queue_manager.py tests/test_queue_migration.py
git commit -m "refactor(queue): split queue_manager into pluggable json backend (no behavior change)"
```

---

## Task 2: Config — DATABASE_URL + cron caps

**Files:**
- Modify: `engine/config.py`
- Test: `tests/test_cron_guard.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cron_guard.py`:

```python
from engine import config

def test_config_has_db_and_cap_knobs():
    assert hasattr(config, "DATABASE_URL")          # None when env unset
    assert isinstance(config.CRON_PER_RUN_CAP_USD, float)
    assert isinstance(config.CRON_MONTHLY_CAP_USD, float)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cron_guard.py::test_config_has_db_and_cap_knobs -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add the config**

In `engine/config.py`, after the cost-tracking block, add:

```python
# ── Shared queue backend (Neon) ───────────────────────────────────────────────
# When set, the queue uses Neon Postgres as the single source of truth (Railway
# cron + local). Unset → the local JSON file (offline/test fallback).
DATABASE_URL = os.environ.get("DATABASE_URL") or None

# ── Ideate cron cost guard (unattended runs only) ─────────────────────────────
CRON_PER_RUN_CAP_USD = float(os.environ.get("CRON_PER_RUN_CAP_USD", "2.0"))
CRON_MONTHLY_CAP_USD = float(os.environ.get("CRON_MONTHLY_CAP_USD", "15.0"))
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cron_guard.py::test_config_has_db_and_cap_knobs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_cron_guard.py
git commit -m "feat(config): add DATABASE_URL + ideate-cron cost-cap knobs"
```

---

## Task 3: Backend selector chooses Neon when DATABASE_URL is set

**Files:**
- Test: `tests/test_queue_contract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_queue_contract.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_queue_contract.py -v`
Expected: FAIL (`ModuleNotFoundError: engine.queue.neon_backend`).

- [ ] **Step 3: Create a minimal importable `neon_backend`**

Create `engine/queue/neon_backend.py` with the imports and a connect helper only (full functions land in Task 5). Importing it must NOT open a connection:

```python
"""Neon Postgres backend for the idea queue (JSONB-document rows).
Mirrors the json_backend contract. No connection is opened at import time."""
import psycopg
from psycopg.types.json import Jsonb
from datetime import datetime, timezone
from engine.config import DATABASE_URL, MIN_VIRAL_SCORE


def _conn():
    return psycopg.connect(DATABASE_URL, autocommit=True)
```

Add `psycopg[binary]` to the project's main-env requirements file (e.g. `requirements.txt`); the `.venv-video` env is untouched.

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_queue_contract.py -v`
Expected: PASS (both selector tests).

- [ ] **Step 5: Commit**

```bash
git add engine/queue/neon_backend.py tests/test_queue_contract.py requirements.txt
git commit -m "feat(queue): backend selector picks neon when DATABASE_URL set"
```

---

## Task 4: Neon schema

**Files:**
- Create: `engine/db/schema_queue.sql`
- Test: `tests/test_queue_contract.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_queue_contract.py`:

```python
from pathlib import Path

def test_schema_defines_ideas_and_costs():
    sql = Path("engine/db/schema_queue.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS ideas" in sql
    assert "data         JSONB" in sql or "data JSONB" in sql
    assert "CREATE TABLE IF NOT EXISTS api_costs" in sql
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_queue_contract.py::test_schema_defines_ideas_and_costs -v`
Expected: FAIL (FileNotFoundError).

- [ ] **Step 3: Create the schema**

Create `engine/db/schema_queue.sql`:

```sql
-- The Untold Game — shared queue schema (Neon). Document-in-Postgres: promoted
-- columns for the queries queue_manager runs + the full idea dict in `data`.
CREATE TABLE IF NOT EXISTS ideas (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',
    viral_score  REAL,
    source_agent TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    data         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ideas_status_score ON ideas (status, viral_score DESC);

-- Durable cost ledger (Railway fs is ephemeral; the monthly cap reads this).
CREATE TABLE IF NOT EXISTS api_costs (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent   TEXT,
    run_id  TEXT,
    usd     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS api_costs_ts ON api_costs (ts);
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_queue_contract.py::test_schema_defines_ideas_and_costs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/db/schema_queue.sql tests/test_queue_contract.py
git commit -m "feat(db): add Neon queue schema (ideas + api_costs)"
```

---

## Task 5: neon_backend — full contract

**Files:**
- Modify: `engine/queue/neon_backend.py`
- Test: `tests/test_queue_contract.py` (append the parametrized contract)

- [ ] **Step 1: Write the failing contract test (parametrized over backends)**

Append to `tests/test_queue_contract.py`:

```python
import os, json, uuid
import pytest
from engine import config
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_queue_contract.py -k roundtrip -v`
Expected: the `json` param PASSES (json_backend already works); add a deliberate assertion against neon by running with a branch later. For now the new tests exercise `json` and FAIL only if neon funcs are missing when `TEST_DATABASE_URL` is set. Without the env var, neon is skipped.

> The point of Task 5 is the neon impl. To verify it, set `TEST_DATABASE_URL` to a Neon **test branch** connection string and re-run; the `neon` param must pass too.

- [ ] **Step 3: Implement the full neon_backend contract**

Replace `engine/queue/neon_backend.py` with:

```python
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
```

- [ ] **Step 4: Verify against a Neon test branch**

Apply the schema to a Neon test branch, then:

```bash
psql "$TEST_DATABASE_URL" -f engine/db/schema_queue.sql
TEST_DATABASE_URL="$TEST_DATABASE_URL" python3 -m pytest tests/test_queue_contract.py -v
```
Expected: both `json` and `neon` params PASS. (Without `TEST_DATABASE_URL`, neon params are skipped and only `json` runs — still green.)

- [ ] **Step 5: Commit**

```bash
git add engine/queue/neon_backend.py tests/test_queue_contract.py
git commit -m "feat(queue): neon backend implements the full queue contract"
```

---

## Task 6: Migration — idea_queue.json → Neon

**Files:**
- Create: `engine/db/migrate_queue.py`
- Test: `tests/test_queue_contract.py` (append)

- [ ] **Step 1: Write the failing test (pure load logic)**

Append:

```python
def test_migrate_loads_ideas_from_json(tmp_path):
    from engine.db import migrate_queue
    p = tmp_path / "idea_queue.json"
    p.write_text(json.dumps([_sample_idea(), _sample_idea()]))
    loaded = migrate_queue.load_ideas(str(p))
    assert len(loaded) == 2
    assert all("id" in i for i in loaded)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_queue_contract.py::test_migrate_loads_ideas_from_json -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the migration**

Create `engine/db/migrate_queue.py`:

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_queue_contract.py::test_migrate_loads_ideas_from_json -v`
Expected: PASS. (Full import is verified manually against a Neon branch: `DATABASE_URL=... python3 -m engine.db.migrate_queue`.)

- [ ] **Step 5: Commit**

```bash
git add engine/db/migrate_queue.py tests/test_queue_contract.py
git commit -m "feat(db): idempotent idea_queue.json -> Neon migration"
```

---

## Task 7: Cost ledger → Neon + guard math

**Files:**
- Modify: `engine/usage.py` (extend `record()`)
- Create: `engine/cron_guard.py`
- Test: `tests/test_cron_guard.py` (append)

- [ ] **Step 1: Write the failing guard-math tests**

Append to `tests/test_cron_guard.py`:

```python
from engine import cron_guard

def test_should_skip_when_month_over_cap():
    assert cron_guard.should_skip_monthly(spent=16.0, cap=15.0) is True
    assert cron_guard.should_skip_monthly(spent=10.0, cap=15.0) is False

def test_over_run_cap():
    assert cron_guard.over_run_cap(run_spent=2.5, cap=2.0) is True
    assert cron_guard.over_run_cap(run_spent=1.0, cap=2.0) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cron_guard.py -k "cap" -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the guard**

Create `engine/cron_guard.py`:

```python
"""Cost-guard math + the durable monthly-spend query for the unattended cron."""
from engine.config import DATABASE_URL


def should_skip_monthly(spent: float, cap: float) -> bool:
    return spent >= cap


def over_run_cap(run_spent: float, cap: float) -> bool:
    return run_spent >= cap


def monthly_spent_usd() -> float:
    """Sum of api_costs over the trailing 30 days (Neon). 0.0 if no DB."""
    if not DATABASE_URL:
        return 0.0
    from engine.queue import neon_backend
    with neon_backend._conn() as c:
        row = c.execute(
            "SELECT COALESCE(sum(usd), 0) FROM api_costs "
            "WHERE ts > now() - interval '30 days'").fetchone()
    return float(row[0])
```

- [ ] **Step 4: Extend `engine/usage.py` to persist costs to Neon**

In `engine/usage.py`, inside `record()` (after the JSONL append), add a best-effort Neon insert. It must never raise (self-stub rule):

```python
    # Durable ledger for the unattended cron's monthly cap (Railway fs is ephemeral).
    try:
        from engine.config import DATABASE_URL
        if DATABASE_URL:
            from engine.queue import neon_backend
            with neon_backend._conn() as c:
                c.execute(
                    "INSERT INTO api_costs (agent, run_id, usd) VALUES (%s,%s,%s)",
                    (stage, _run_id(), cost_usd(u, model)))
    except Exception as e:                       # never crash a production run
        print(f"cost-track warning: neon ledger write failed: {e}")
```

(Place this inside the existing `try` body of `record()` or a sibling `try` so a DB error is swallowed, matching the existing best-effort contract.)

- [ ] **Step 5: Run guard tests to verify they pass**

Run: `python3 -m pytest tests/test_cron_guard.py -k "cap" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/cron_guard.py engine/usage.py tests/test_cron_guard.py
git commit -m "feat(cron): cost-guard math + durable Neon api_costs ledger"
```

---

## Task 8: run_cron entrypoint

**Files:**
- Create: `engine/run_cron.py`
- Test: `tests/test_cron_guard.py` (append)

- [ ] **Step 1: Write the failing orchestration tests**

Append to `tests/test_cron_guard.py`:

```python
from engine import run_cron

def test_cron_skips_when_monthly_cap_exceeded(monkeypatch):
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: 99.0)
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 15.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 0 and ran == []          # skipped cleanly, no agents ran

def test_cron_runs_all_four_when_under_caps(monkeypatch):
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: 0.0)
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 15.0)
    monkeypatch.setattr(run_cron.config, "CRON_PER_RUN_CAP_USD", 2.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 0 and ran == [1, 2, 3, 4]

def test_cron_stops_remaining_agents_when_per_run_cap_hit(monkeypatch):
    # spend grows past the per-run cap right after the first agent
    seq = iter([0.0, 5.0, 5.0, 5.0, 5.0])      # before-run, then after each agent
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: next(seq))
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 100.0)
    monkeypatch.setattr(run_cron.config, "CRON_PER_RUN_CAP_USD", 2.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 2 and ran == [1]              # stopped after the first agent
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cron_guard.py -k cron_ -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement run_cron**

Create `engine/run_cron.py`:

```python
"""Unattended ideate cron (Railway). Cost-guarded; writes to Neon via the queue
backend. NEVER renders — produce/render stay local. Schedule ~every 2-3 days.

Agents run SEQUENTIALLY so the per-run cap can stop the remaining agents the
moment this run's spend crosses the cap (spec §5)."""
import sys
from engine import config, cron_guard
from engine.run_pipeline import run_single_agent

AGENTS = (1, 2, 3, 4)   # 1=history 2=trending 3=gaps 4=evergreen


def main() -> int:
    spent0 = cron_guard.monthly_spent_usd()
    if cron_guard.should_skip_monthly(spent0, config.CRON_MONTHLY_CAP_USD):
        print(f"[cron] skip: 30-day spend ${spent0:.2f} ≥ cap ${config.CRON_MONTHLY_CAP_USD:.2f}")
        return 0
    print(f"[cron] start: 30-day spend ${spent0:.2f}; per-run cap "
          f"${config.CRON_PER_RUN_CAP_USD:.2f}")
    for n in AGENTS:
        run_single_agent(n)
        run_spent = max(0.0, cron_guard.monthly_spent_usd() - spent0)
        if cron_guard.over_run_cap(run_spent, config.CRON_PER_RUN_CAP_USD):
            print(f"[cron] per-run cap hit after agent {n} (${run_spent:.2f} ≥ "
                  f"${config.CRON_PER_RUN_CAP_USD:.2f}); stopping remaining agents")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> Agents run sequentially (not parallel) specifically so the per-run cap can halt remaining agents mid-run, as the spec requires. Wall-clock doesn't matter for an unattended cron. The monthly ceiling remains the primary runaway guard.

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cron_guard.py -k cron_ -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (JSON path; neon params skipped without `TEST_DATABASE_URL`).

- [ ] **Step 6: Commit**

```bash
git add engine/run_cron.py tests/test_cron_guard.py
git commit -m "feat(cron): run_cron entrypoint — guarded 4-agent ideate run"
```

---

## Task 9: Docs — ADR + CLAUDE.md + Railway notes

**Files:**
- Create: `docs/adr/0006-neon-queue-railway-cron.md`
- Modify: `CLAUDE.md` (deploy section)

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0006-neon-queue-railway-cron.md` capturing: context (ideas-while-laptop-off), decision (Neon single source of truth when `DATABASE_URL` set; JSON fallback; Railway cron every 2-3 days running the 4 agents sequentially; cost guard = rolling-30-day monthly ceiling (skip) + per-run cap that stops remaining agents; render stays local), consequences (psycopg dep; one shared store; sequential agents trade wall-clock for the per-run cap), and the deferred items (videos/metrics, Vercel dashboard, multi-channel, Upstash).

- [ ] **Step 2: Update CLAUDE.md deploy section**

In `CLAUDE.md`, update the Deploy paragraph to state: the ideate cron runs on Railway every 2-3 days writing to **Neon** (single source of truth when `DATABASE_URL` is set); local produce/review/render read the same Neon queue; **render is still local** (Railway can't render); the JSON queue is the offline/test fallback. Note the Railway start command `python3 -m engine.run_cron` and required env (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `CRON_*_CAP_USD`).

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0006-neon-queue-railway-cron.md CLAUDE.md
git commit -m "docs: ADR-0006 Neon queue + Railway ideate cron; CLAUDE.md deploy update"
```

---

## Task 10: Provisioning + final verification (ops, after merge)

> These are operational steps, not code. Do them via the Railway MCP / Neon dashboard once the PR is merged. Listed so nothing is dropped.

- [ ] Apply `engine/db/schema_queue.sql` to the **production** Neon database.
- [ ] Run `DATABASE_URL=<neon> python3 -m engine.db.migrate_queue` to import the current `idea_queue.json`.
- [ ] Locally set `DATABASE_URL` in `.env`; verify `python3 -m engine.run_pipeline --review` reads the Neon queue and a produce/approve round-trips.
- [ ] Create the Railway service from `main`: start `python3 -m engine.run_cron`; env `DATABASE_URL`, `ANTHROPIC_API_KEY` (reuse CF's), `CRON_PER_RUN_CAP_USD`, `CRON_MONTHLY_CAP_USD`; cron schedule ~every 2-3 days (e.g. `0 9 */2 * *`). **Do not** deploy render to Railway.
- [ ] Confirm one cron run stocks Neon and the local machine sees the new pending ideas.

---

## Final checks before PR

- [ ] `python3 -m pytest tests/ -q` green (JSON path).
- [ ] With a Neon test branch: `TEST_DATABASE_URL=... python3 -m pytest tests/test_queue_contract.py` green for both params.
- [ ] Ship via `ship-video-change`: dual adversarial review (Codex + Claude), 0 Critical / 0 Important, PR with `Adversarial-Reviewed:` trailer, squash-merge.
