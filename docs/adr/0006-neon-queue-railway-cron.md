# ADR 0006 — Neon-backed shared idea queue + Railway ideate cron

**Status:** Accepted / LIVE (2026-06-14)

## Context

Idea generation only runs when the local M5 is awake. The queue stalls whenever
the laptop is off, creating a dependency on the user's schedule that defeats the
point of automation. The user already runs Railway (for other crons) and NeonDB
(for ConvictionFinder) — both are available at no extra standing cost.

The prior queue was `queue/idea_queue.json` — a local file managed by
`engine/queue_manager.py`. A Railway cron writing ideas cannot reach a local file,
so the queue must move to a shared, cloud-accessible store. Upstash Redis was
evaluated but deferred: Neon Postgres is already in the account and the
document-in-Postgres model handles the queue's JSONB-merge update pattern cleanly.

## Decision

**When `DATABASE_URL` is set, Neon Postgres is the single source of truth for the
idea queue.** Both the Railway ideate cron *and* all local flows (review, produce,
render handoff) read from and write to the same Neon `ideas` table. The local JSON
file (`queue/idea_queue.json`) remains the offline/test fallback when `DATABASE_URL`
is unset — the queue layer is backend-pluggable behind the existing `queue_manager`
public API, so no consumer changes.

**Schema:** document-in-Postgres — promoted columns (`id`, `status`, `viral_score`,
`source_agent`, `created_at`) for the only queries the queue runs (filter by status,
sort by score), plus a `data JSONB` column that carries the full idea dict.
`update_idea()` is a JSONB merge; no schema migration is needed when new fields are
added to an idea.

**Cron:** a Railway service runs `python3 -m engine.run_cron` every 2-3 days. It
executes all 4 ideate agents **sequentially** (trading wall-clock time for a
predictable per-run cost envelope) and writes new ideas directly to Neon via
`add_idea()`. The Railway filesystem is ephemeral, so cost spend is persisted to a
durable Neon `api_costs` table alongside the ideas.

**Cost guard (two levels):**
1. *Monthly ceiling* — before the run starts, sum `api_costs` over the trailing 30
   days; if spend ≥ `CRON_MONTHLY_CAP_USD`, log and exit 0 (skipped, not failed).
2. *Per-run cap* — track accumulated USD during the run; if ≥ `CRON_PER_RUN_CAP_USD`,
   stop remaining agents and exit non-zero so Railway flags the partial run.

**Error stance:** if Neon is unreachable when `DATABASE_URL` is set, operations
raise and the cron exits non-zero. There is no silent fallback to JSON — that would
fork the source of truth.

**Render stays local.** Railway never renders. The 45-min Chromium render runs on
the M5 via launchd; Railway's ideate cron only runs the fast, API-bound generation step.

## Consequences

- **New dependency:** `psycopg` (Postgres driver) in the main `python3` environment
  only. The `.venv-video` render environment is untouched.
- **Race condition eliminated:** one Postgres store replaces the local JSON file;
  concurrent writers (Railway + local) are handled natively by Postgres.
- **Sequential agent execution:** agents run one-at-a-time in the cron (not
  parallel as in the local `run_pipeline`). This is intentional — the per-run cap
  stops cleanly between agents rather than partway through a parallel fan-out.
- **JSON path unchanged:** with `DATABASE_URL` unset, the pipeline behaves exactly
  as before; all existing pytest tests pass without external dependencies.
- **Deferred (out of scope):** the `videos` / `metrics` learning-loop tables
  (Stage 3); the Vercel review dashboard; the multi-channel de-hardcode-sports
  refactor; Upstash Redis.
