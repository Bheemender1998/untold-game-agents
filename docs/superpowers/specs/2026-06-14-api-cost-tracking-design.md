# API cost tracking for automation runs — design

**Date:** 2026-06-14
**Status:** Approved (brainstorm) → ready for implementation plan
**Branch:** `feat/api-cost-tracking`

## Problem

The overnight automation (`scripts/overnight.sh`, launchd `com.untoldgame.overnight`,
daily 01:00) makes Anthropic API calls across ideation + production, but **captures zero
cost telemetry**. The 2026-06-14 run revealed this the hard way: production failed on a
"credit balance too low" error with no prior warning, because nothing tracked spend.
The user wants per-run cost visibility (ledger + trend history) plus a budget alert so a
runaway or an approaching-empty balance is visible *before* a run dies.

There are 8 Anthropic call sites across 5 files, each constructing its own
`anthropic.Anthropic(max_retries=5)` client and calling `messages.create(...)`. None read
`resp.usage`. Model is `claude-sonnet-4-6`.

| File | Line(s) | Stage label |
|------|---------|-------------|
| `engine/ideate/base_agent.py` | 58 | `ideate` |
| `engine/pipeline/fact_gate.py` | 32 | `fact_check` |
| `engine/pipeline/metadata.py` | 76, 118, 164 | `metadata` |
| `engine/video/compose.py` | 67, 281 | `script` / `compose` |
| `engine/pipeline/thumbnail.py` | 201 | `thumbnail` |

(Exact stage names per call site to be finalized during implementation by reading each
call's purpose; the table is the starting map.)

## Decisions (from brainstorm)

- **Output:** persistent ledger + per-run summary + budget alert.
- **Alert action:** warn only — loud `⚠️ BUDGET` line in log + ledger; never stops the run.
- **Threshold:** `COST_ALERT_USD = 10.0` per run (config constant, tunable once real runs
  establish a baseline). Estimated normal run is ~$3–6.

## Architecture

### New module: `engine/usage.py`

The single place that knows how to price a response and append to the ledger.

**Pricing table** (per-token USD, sourced from the `claude-api` reference, 2026-06):

```python
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,   # 1.25 × input
        "cache_read":  0.30 / 1_000_000,   # 0.10 × input
    },
}
```

**`logged_create(client, stage, **kwargs)`** — the wrapper every call site uses:

1. `resp = client.messages.create(**kwargs)` — the API call itself is NOT wrapped in
   try/except; a real API failure must propagate exactly as it does today.
2. In a `try/except` that swallows all errors (self-stub rule): read `resp.usage`, compute
   USD via `PRICING[_pricing_key(resp.model)]` — the API returns a resolved *dated* id
   (e.g. `claude-haiku-4-5-20251001`) while `PRICING` is keyed on the alias, so a trailing
   `-YYYYMMDD` is stripped before the lookup (fall back to a 0-cost row + warning if the
   model is still unknown). The ledger row stores the raw `resp.model` for fidelity. Append
   one JSON line to the ledger.
3. `return resp` — untouched.

**Ledger: `logs/api-cost.jsonl`** — one row per call:

```json
{"ts": "2026-06-14T01:02:33", "run_id": "2026-06-14T01:00:00", "stage": "script",
 "model": "claude-sonnet-4-6", "input_tokens": 8021, "output_tokens": 6210,
 "cache_creation_input_tokens": 0, "cache_read_input_tokens": 4096, "cost_usd": 0.117}
```

- `run_id` comes from env var `TUG_RUN_ID`; defaults to `"adhoc-<YYYY-MM-DD>"` when unset
  (manual `run_produce` / `run_pipeline` invocations still get logged, just not grouped
  under an overnight run).
- `ts` is stamped at write time (`datetime.now().isoformat(timespec="seconds")`).
- Append mode, one `write()` of a single line, so the two concurrent overnight processes
  (ideate, then produce — actually sequential, but agents inside ideate run in parallel
  threads in one process) don't interleave partial rows.

### New module: `engine/run_cost_report.py`

CLI: `python3 -m engine.run_cost_report [--run <run_id>]`.

- Reads `logs/api-cost.jsonl`. If `--run` given, filters to that `run_id`; else defaults to
  today's `TUG_RUN_ID` (or all of today's rows if no run id).
- Aggregates by `stage`: call count, summed input/output/cache tokens, summed USD.
- Prints a per-stage table + run total (see Data flow below).
- If run total > `config.COST_ALERT_USD`, prints `⚠️ BUDGET: run cost $X exceeds $Y cap`.
- Empty/missing ledger → prints "no cost data for this run", **exits 0** (never blocks the
  overnight run). Exit code is always 0 — this is a reporter, not a gate.

### Config: `engine/config.py`

Add two constants:

```python
COST_ALERT_USD = 10.0          # per-run budget alert threshold (warn only)
COST_LEDGER_PATH = "logs/api-cost.jsonl"
```

(Pricing lives in `usage.py`, not config — it's implementation detail of the pricer.)

### Orchestration: `scripts/overnight.sh`

- Export `TUG_RUN_ID="$(date +%Y-%m-%dT%H:%M:%S)"` once, before the python calls, so every
  call in the night shares one run id.
- After the produce step, add a final line:
  `python3 -m engine.run_cost_report --run "$TUG_RUN_ID" || true` so the summary + any
  `⚠️ BUDGET` warning land in the daily log. `|| true` guarantees the reporter can never
  fail the run.

### Call-site change (mechanical, ×8)

```python
# before
resp = client.messages.create(model=MODEL, max_tokens=..., messages=...)
# after
from engine.usage import logged_create
resp = logged_create(client, "script", model=MODEL, max_tokens=..., messages=...)
```

No other behavior changes at the call sites.

## Data flow (one overnight run)

1. `overnight.sh` sets `TUG_RUN_ID=2026-06-14T01:00:00`.
2. `run_pipeline` (ideate) → 4 agents each `logged_create(..., "ideate")` → ledger rows.
3. `run_auto` (produce) → per video: `script`, `fact_check`, `metadata`, `thumbnail` rows,
   same `run_id`.
4. `run_cost_report --run 2026-06-14T01:00:00` →

```
── API cost — run 2026-06-14T01:00:00 ──
  ideate       12 calls   312k in    48k out   $0.91
  script        3 calls   240k in   180k out   $3.42
  fact_check    3 calls    96k in    24k out   $0.65
  metadata      3 calls    30k in     6k out   $0.18
  thumbnail     3 calls     9k in     2k out   $0.06
  ───────────────────────────────────────────────────
  TOTAL        24 calls                        $5.22
```

and, if over cap: `⚠️ BUDGET: run cost $12.40 exceeds $10.00 cap`.

## Error handling

- **`logged_create`:** only the *recording* is wrapped in `try/except Exception` → on
  failure prints a one-line `cost-track warning: …` and returns `resp` anyway. The
  `messages.create` call is outside the try, so API errors propagate unchanged.
- **Reporter:** missing/empty/corrupt ledger → "no cost data", exit 0. A malformed JSON
  line is skipped with a warning, not fatal.
- **Ledger write:** append-mode single-line write; failure is swallowed by the recorder's
  try/except.

## Testing (`tests/test_usage.py`, pytest, main `python3` env)

- `cost_usd` computation: known tokens × known rates → exact expected USD, incl. cache
  creation + cache read tokens.
- Unknown model → 0 cost + warning, no raise.
- `logged_create` with a mocked client/response: writes a parseable row carrying the
  `run_id` from a patched `TUG_RUN_ID` env.
- Reporter aggregation: seed a temp ledger with two `run_id`s → summary sums only the
  requested run; per-stage call counts and USD correct.
- Threshold: total just under cap → no warning line; just over → warning line present.
- Self-stub: a recorder whose ledger write raises still returns the response (run
  unaffected).

## Files touched

| File | Change |
|------|--------|
| `engine/usage.py` | **new** — pricing table, `logged_create`, `record` |
| `engine/run_cost_report.py` | **new** — aggregate + print + threshold check |
| `engine/config.py` | +`COST_ALERT_USD`, +`COST_LEDGER_PATH` |
| `engine/ideate/base_agent.py` | route call through `logged_create` |
| `engine/pipeline/fact_gate.py` | "" |
| `engine/pipeline/metadata.py` | "" (3 call sites) |
| `engine/video/compose.py` | "" (2 call sites) |
| `engine/pipeline/thumbnail.py` | "" |
| `scripts/overnight.sh` | export `TUG_RUN_ID`, append `run_cost_report` call |
| `tests/test_usage.py` | **new** |
| docs | update `CLAUDE.md` entrypoints (new `run_cost_report` command) + any doc the staleness gate flags |

## Out of scope (YAGNI)

- Hard budget cap / aborting a run mid-flight (explicitly chose warn-only).
- Per-video or per-idea cost attribution (stage-level is enough for now).
- A dashboard / web view of the ledger (jsonl is queryable; revisit if a trend view is
  wanted later).
- Tracking non-Anthropic costs (none today).
