# Design: Neon-backed shared idea queue + Railway ideate cron

**Date:** 2026-06-14
**Status:** Approved design — ready for implementation plan
**Motivation:** generate ideas on a schedule while the local machine is off, with a single shared queue both the cloud cron and the local pipeline read/write.

## Problem

Idea generation only happens when the M5 is awake. The user wants the queue stocked on a schedule regardless of whether the laptop is on. The user already runs Railway, NeonDB, Vercel, and Upstash Redis for other projects.

The current queue is `queue/idea_queue.json` — a local JSON file managed by `engine/queue_manager.py`. A cloud cron writing ideas can't reach a local file, so the queue must move to a shared store.

## Decisions (locked during brainstorming)

1. **Source of truth:** when `DATABASE_URL` is set, **Neon Postgres is the single source of truth** for all environments (Railway cron *and* local produce/review/render). JSON remains the offline/test fallback when `DATABASE_URL` is unset.
2. **Cron cadence:** **every 2-3 days, all 4 agents** (batch refresh; lower standing cost than daily).
3. **Cost guard:** **per-run cap + rolling-30-day monthly ceiling** — abort a run over the per-run cap, skip a run entirely when the trailing-30-day spend exceeds the monthly ceiling.
4. **Data model:** **document-in-Postgres** (promoted columns + `data JSONB`), not normalized relational.
5. **DB failure stance:** **fail loud, no silent fallback** to JSON when `DATABASE_URL` is set.
6. **Cost ledger durability:** also persist priced rows to Neon (`api_costs` table) so the monthly cap survives Railway's ephemeral filesystem.

## Scope

**In:**
- Pluggable queue backend behind the existing `queue_manager` API (JSON | Neon).
- Neon schema + idempotent migration of `idea_queue.json`.
- Railway-deployable ideate cron (`run_cron`) on the 2-3 day cadence.
- Cost guard (per-run + rolling-30-day) backed by a durable Neon cost ledger.

**Out (explicitly deferred — do not touch):**
- The `videos` / `metrics` learning-loop tables (Stage 3).
- The Vercel review dashboard.
- The multi-channel (de-hardcode-sports) refactor.
- Upstash Redis.
- **Anything in render** — render stays local on the M5 (Railway cannot do the 45-min Chromium render).

## Data model

The live queue is schemaless: `update_idea(idea_id, **fields)` merges arbitrary fields over a run's life (`script_path`, fact-gate verdicts, `long_youtube_url`, `short_youtube_url`, …). A normalized schema would require a migration per new field, so use a **document row**:

```sql
CREATE TABLE IF NOT EXISTS ideas (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|in_production
    viral_score  REAL,
    source_agent TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    data         JSONB NOT NULL                     -- the full idea dict
);
CREATE INDEX IF NOT EXISTS ideas_status_score ON ideas (status, viral_score DESC);

CREATE TABLE IF NOT EXISTS api_costs (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent      TEXT,
    run_id     TEXT,
    usd        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS api_costs_ts ON api_costs (ts);
```

Promoted columns (`status`, `viral_score`, `source_agent`, `created_at`) cover the only queries `queue_manager` runs (filter by status, sort by viral score). `data` JSONB preserves full flexibility — `update_idea` is a JSONB merge.

The legacy `engine/db/schema.sql` `videos`/`metrics` tables stay in the repo but remain **unused** (Stage 3). The `ideas` table above supersedes the narrow relational `ideas` definition there for queue purposes.

## Architecture

`queue_manager` becomes a thin dispatcher; **public functions and signatures are unchanged**, so no consumer changes (`engine/ideate/*`, `run_pipeline`, `run_auto`, `run_produce`, `run_subject`, `run_video`).

```
engine/queue/
  __init__.py        # selector: neon_backend if DATABASE_URL else json_backend
  json_backend.py    # today's JSON impl, moved verbatim (atomic temp-file write)
  neon_backend.py    # Postgres impl (psycopg), JSONB-doc model
engine/queue_manager.py   # re-exports the selected backend's functions + new_idea() (pure, backend-agnostic)
```

Backend contract (the existing surface): `add_idea`, `get_pending`, `approve`, `reject`, `mark_in_production`, `get_by_status`, `get_by_id`, `update_idea`, `stats`, `split_youtube_url_field`. `new_idea()` is a pure constructor and stays in `queue_manager` (no I/O).

**Config (`engine/config.py`):**
- `DATABASE_URL` — Neon connection string from `.env` / Railway env. Unset → JSON backend.
- `CRON_PER_RUN_CAP_USD`, `CRON_MONTHLY_CAP_USD` — cron cost caps.

**Migration:** `python3 -m engine.db.migrate_queue` — idempotent upsert of every idea in `idea_queue.json` into Neon (`INSERT … ON CONFLICT (id) DO UPDATE`). Safe to re-run; reports counts.

**Cron entry:** `python3 -m engine.run_cron`:
1. Guard: sum `api_costs` over trailing 30 days; if ≥ `CRON_MONTHLY_CAP_USD` → log + exit 0 (skipped).
2. Run all 4 agents (the existing `run_all_agents`, no review), each Anthropic call priced + written to `api_costs`.
3. If this run's accumulated cost ≥ `CRON_PER_RUN_CAP_USD` → stop remaining agents, exit non-zero.
With `DATABASE_URL` set, `add_idea()` writes to Neon.

## Data flow

```
Railway cron (every 2-3d) → 4 agents → add_idea() → Neon ideas (status=pending)
Local (DATABASE_URL set):
  run_pipeline --review → get_pending() from Neon → approve → status=approved (Neon)
  run_auto/produce → reads approved → renders LOCALLY → update_idea(paths, youtube_urls) → Neon
```

One store, two writers (Railway + local); Postgres handles concurrency natively, removing the JSON multi-writer race.

## Cost guard

- Source of truth for spend = the Neon `api_costs` table (durable across Railway's ephemeral filesystem). `engine/usage.py`'s `logged_create` is extended to also insert a priced row into `api_costs` when `DATABASE_URL` is set (keep the existing `logs/api-cost.jsonl` for local/attended runs).
- **Monthly ceiling:** before a cron run, `SELECT sum(usd) FROM api_costs WHERE ts > now() - interval '30 days'`; skip if ≥ cap.
- **Per-run cap:** track the run's own accumulated USD; abort remaining agents when ≥ cap.
- Cap math lives in a small pure function (`should_skip(monthly_spent, cap)`, `over_run_cap(run_spent, cap)`) so it is unit-testable without a network.

## Error handling

- **Neon unreachable** with `DATABASE_URL` set → operations raise; cron exits non-zero (visible failed run in Railway); local commands error out. **No silent fallback to JSON** — that would fork the source of truth.
- Agent-level self-stubbing still holds (one agent failing must not crash the whole cron run), but **DB-write failures surface** (they are not agent-content failures).
- Migration is idempotent (upsert).

## Testing

- Default pytest env has **no `DATABASE_URL`** → JSON backend → **all existing tests pass unchanged**.
- **Backend contract tests:** parametrized over backends — JSON always; Neon only when `TEST_DATABASE_URL` (a Neon test branch) is set, otherwise skipped. Same assertions for both (add → get_pending → approve → update_idea round-trips, status transitions, score sort).
- **Cost-guard math:** unit-tested with a synthetic ledger, no network.
- Contract: `python3 -m pytest tests/ -q` is green on the JSON path with zero new external deps required to run the suite.

## Deploy / docs

- **Railway service** from `main`: start command `python3 -m engine.run_cron`; env = `DATABASE_URL` (Neon) + reused `ANTHROPIC_API_KEY` (CF's key) + `CRON_PER_RUN_CAP_USD` + `CRON_MONTHLY_CAP_USD`; Railway cron schedule ≈ every 2-3 days. **Render is never deployed to Railway.**
- **Docs:** update the CLAUDE.md deploy section (Neon queue + Railway ideate cron; render stays local) and add a short ADR recording the decision. Per the keep-docs-in-sync rule, this happens in the same change.

## New dependency

`psycopg` (Postgres driver) for the `python3` main env only. The `.venv-video` render env is untouched.

## Success criteria

1. With `DATABASE_URL` unset, the pipeline behaves exactly as today (JSON), tests green.
2. With `DATABASE_URL` set, `add_idea`/`get_pending`/`approve`/`update_idea` round-trip through Neon; the existing local flows (review, produce, auto) work against Neon with no caller code changes.
3. `migrate_queue` imports the current `idea_queue.json` into Neon idempotently.
4. `run_cron` runs all 4 agents, writes to Neon, respects both caps, and persists costs to `api_costs`.
5. A Railway cron on the 2-3 day cadence stocks the Neon queue while the laptop is off; the user reviews/produces locally against the same queue.
