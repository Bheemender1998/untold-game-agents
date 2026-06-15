# Design: Cost controls — light-stage model routing + Neon-aware cost readout

**Date:** 2026-06-15
**Status:** Approved design — ready for implementation plan
**Motivation:** trim the cheap, mechanical Anthropic calls onto a cheaper model, and make the cost readout show the *complete* spend including the Railway cron (whose cost only lands in Neon).

## Context

All Anthropic calls use the global `config.MODEL = "claude-sonnet-4-6"`. The real spend is `fact_check` (the integrity gate) and `script_writer` — both stay on Sonnet for quality/integrity. A handful of mechanical, never-or-barely-viewer-facing stages are safe to run on the cheaper Haiku model.

Separately: the Railway ideate cron writes its cost rows **only to the Neon `api_costs` table** (Railway's filesystem is ephemeral, so the local `logs/api-cost.jsonl` never sees the cron's spend). `run_cost_report` reads only the JSONL, so it cannot show the cron's cost. The complete ledger is Neon.

## Scope

**In:**
- A second model knob `config.MODEL_LIGHT` and routing of 4 mechanical stages to it.
- Haiku pricing in `engine/usage.py` so the cost ledger prices those calls correctly.
- A `--neon` mode for `run_cost_report` that summarizes the Neon `api_costs` table.

**Out (explicitly unchanged — stays on Sonnet / untouched):**
- `fact_check` (ADR-0005 integrity gate — a cheaper judge risks false-passes; never touch), `script_writer`, `thumbnail` tension-line, main `metadata` title, `storyboard`, `headlines`. No fact-gate behavior changes.

**Expectation:** savings are modest (~$0.20–0.30 per produce) — the big costs are deliberately left on Sonnet. This is safe free money, not a major lever.

## Part A — light-stage model routing

- Add to `engine/config.py`:
  ```python
  MODEL_LIGHT = os.environ.get("MODEL_LIGHT", "claude-haiku-4-5")
  ```
- Route exactly these 4 stages to `MODEL_LIGHT`:
  - `short_title` — `engine/pipeline/metadata.py:119` (currently `model=MODEL`) → `model=MODEL_LIGHT`.
  - `short_desc` — `engine/pipeline/metadata.py:165` (currently `model=MODEL`) → `model=MODEL_LIGHT`.
  - `subject` photo-query — `engine/pipeline/subject.py:34` (currently `model=MODEL`) → `model=MODEL_LIGHT`.
  - `companion_tease_writer` — `engine/pipeline/script.py` agent. It runs through `BaseAgent._call`, which hardcodes `config.MODEL`. Add a `self.model` hook:
    - In `engine/ideate/base_agent.py` `BaseAgent.__init__`: `self.model = MODEL` (import `MODEL` from config).
    - In `BaseAgent._call`: use `self.model` instead of the module-level `MODEL` in the `kwargs["model"]`.
    - In the `companion_tease_writer` agent's `__init__`: set `self.model = MODEL_LIGHT`.
    - The 4 ideate agents inherit the default `self.model = MODEL` — **no behavior change** for them.
- **Pricing:** add a `claude-haiku-4-5` entry to `PRICING` in `engine/usage.py`. Use the per-token rates from the `claude-api` reference (confirm during implementation; expected Haiku 4.5 ≈ input $1/M, output $5/M, cache-write 1.25×input, cache-read 0.10×input). Without this, `cost_usd()` returns 0.0 and logs an "unknown model" warning for every Haiku call.

## Part B — Neon-aware cost readout

- Add a pure `summarize_neon(rows)` to `engine/run_cost_report.py` that aggregates `(agent, usd, ts)` rows into: total, by-stage (agent) spend+count, and trailing-30-day total (the figure the monthly cap watches).
- Add a `--neon` flag to `main()`:
  - If `config.DATABASE_URL` is set: query `SELECT agent, usd, ts FROM api_costs` via `engine.queue.neon_backend._conn()`, pass to `summarize_neon`, render.
  - If unset: print a clear error ("--neon requires DATABASE_URL") and exit non-zero.
- The default (no `--neon`) JSONL path is unchanged.
- Why it matters: this is the only way to see the **Railway cron's** spend (Neon-only) and the true trailing-30-day total the cap enforces.

## Error handling

- `MODEL_LIGHT` defaults are pure config; no failure surface.
- Pricing: a missing Haiku entry is the failure mode this fixes; with it added, `cost_usd` is correct.
- `--neon` with no DB → explicit error, not a crash. Neon query failure surfaces (read-only readout; no silent zero).

## Testing

- `config.MODEL_LIGHT` exists and defaults to a Haiku id.
- The 4 routed call sites reference `MODEL_LIGHT` (assert via source/inspection or by monkeypatching and capturing the `model` kwarg passed to `logged_create`).
- `BaseAgent` honors `self.model`: default equals `config.MODEL`; an instance that sets `self.model` uses it in `_call` (capture the kwarg with a stubbed client).
- `usage.cost_usd(usage, "claude-haiku-4-5")` returns a nonzero value matching the wired rates.
- `summarize_neon` over synthetic rows produces correct total / by-stage / trailing-30-day numbers (no DB needed). Optional live integration gated on `TEST_DATABASE_URL`.
- Full suite green under `python3 -m pytest tests/ -q` (JSON path; the pre-existing flaky `test_fact_gate_oracle` live test is deselected/ignored).

## Success criteria

1. The 4 mechanical stages run on Haiku; everything else (esp. fact_check, script_writer) unchanged on Sonnet.
2. The cost ledger prices Haiku calls correctly (nonzero, no "unknown model" warning).
3. `run_cost_report --neon` shows total + by-stage + trailing-30-day from Neon, including the cron's spend.
4. No fact-gate / integrity behavior change. Existing tests pass.
