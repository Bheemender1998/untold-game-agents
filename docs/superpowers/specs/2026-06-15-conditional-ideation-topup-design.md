# Conditional Ideation Top-up — design

**Date:** 2026-06-15
**Status:** approved (brainstorm → spec)
**Branch:** `feat/conditional-ideation-topup`

## Problem

Idea generation runs on two schedulers that both write to the same shared Neon queue:

- **Local overnight** (`scripts/overnight.sh`, launchd `com.untoldgame.overnight`, daily 01:00):
  step 1 runs `run_pipeline --no-review` (all 4 agents, **parallel, uncapped**), then
  produces/renders the top 3 pending ideas.
- **Railway cron** (`railway.json` `0 9 */2 * *`, ~every 2 days): `run_cron` runs the 4
  agents **sequentially under a $2/run + $15/30-day cap**, ideas only, never renders.

Verified state (2026-06-15): the queue holds **77 pending** ideas (95 total, avg viral 8.9).
Render throughput is ≤3 publishable/night. So the queue is already ~25+ nights deep and
growing. The 6/15 overnight cost log shows the nightly ideation portion is **~$1.95** of the
$3.05 run (`competitor_gap $0.76 + sports_history $0.50 + trending $0.36 + evergreen $0.33`) —
~64% of nightly spend, generating ideas onto a backlog that won't be touched for weeks.

The daily local generation is redundant: the Railway cron already tops up every ~2 days, and
the queue is far deeper than throughput consumes.

## Goal

Stop generating ideas locally **every** night. The local overnight should generate **only when
the shared pending queue is below a floor** (default 12); otherwise it skips straight to
produce → render → QC against the existing queue. The Railway cron remains the primary
generator and the safety net.

Outcome: in steady state (queue ≫ 12) the local ideation never fires, saving ~$1.95/night of
uncapped spend; but if the Railway cron silently fails (it had one billing failure on 6/14 and
deploys via a drift-prone tarball), the local run auto-refills before the queue can drain.

## Non-goals

- **Selection logic is unchanged.** `run_auto._select(count) = q.get_pending()[:count]` already
  takes the top-`count` pending ideas ranked by `viral_score DESC` (verified in both
  `engine/queue/neon_backend.py` and `engine/queue/json_backend.py`). Produce keeps draining
  the queue highest-score-first; this change only affects the *supply* of new ideas, never how
  produce picks from them.
- **The Railway cron is untouched.** `run_cron` imports `run_single_agent` directly (not
  `main()`), so it is unaffected by the new flag. It stays the capped primary generator. No
  depth guard is added to the cloud cron (it is already cost-capped and is the fallback).
- No change to render, QC, fact-gate, or the pre-flight lint.

## Design

### New config constant — `engine/config.py`

```python
IDEATE_TOPUP_MIN = int(os.environ.get("IDEATE_TOPUP_MIN", "12"))  # local overnight tops up
# the idea queue only when fewer than this many ideas are pending; else it skips ideation.
```

Single source of truth, env-overridable. Default **12** (~4 nights of render buffer).

### New flag — `run_pipeline.py`

```python
parser.add_argument("--ensure-min", nargs="?", type=int, const=config.IDEATE_TOPUP_MIN,
                    default=None,
                    help="only generate if fewer than N ideas are pending (bare flag uses "
                         "config.IDEATE_TOPUP_MIN); otherwise skip ideation (exit 0)")
```

- Bare `--ensure-min` → floor = `config.IDEATE_TOPUP_MIN` (12).
- `--ensure-min 6` → explicit override.
- Flag absent → `default=None` → **no guard**, today's behavior preserved (manual
  `run_pipeline` and `run_pipeline --agent N` always generate).

### Guard logic — `run_pipeline.py main()`

A pure helper holds the decision so it is testable without argparse or a DB:

```python
def _topup_needed(pending_count: int, floor: int) -> bool:
    """Generate ideas only when the queue is below the floor."""
    return pending_count < floor
```

In `main()`, after the `--stats` and `--review` short-circuits and before agent dispatch
(currently `run_pipeline.py:201`):

```python
if args.ensure_min is not None:
    pending = len(get_pending())
    if not _topup_needed(pending, args.ensure_min):
        print(f"{GRAY}Queue has {pending} pending ≥ floor {args.ensure_min} — "
              f"skipping ideation.{RESET}")
        return
    print(f"{GRAY}Queue has {pending} pending < floor {args.ensure_min} — topping up.{RESET}")
```

`get_pending()` is already imported (`run_pipeline.py:25`) and returns the full pending list
from the active backend (Neon or JSON). One count per run — negligible cost.

### `scripts/overnight.sh` change

Step 1 changes from:
```bash
python3 -m engine.run_pipeline --no-review || echo "(ideate failed — non-fatal, continuing)"
```
to:
```bash
python3 -m engine.run_pipeline --no-review --ensure-min || echo "(ideate failed — non-fatal, continuing)"
```
(produce/render/QC step 2 is untouched). The threshold lives in `config.IDEATE_TOPUP_MIN`, not
in the shell.

## Testing (TDD)

In `tests/` (force the JSON backend so it never hits Neon, matching the existing pattern):

- `_topup_needed`: `True` when `count < floor`; `False` when `count > floor`; **boundary**
  `count == floor` → `False` (≥ floor means skip).
- **Skip path:** monkeypatch `run_pipeline.get_pending` to return 20 stub ideas and
  `run_all_agents` to a spy; call `main()` with `argv = ["--no-review", "--ensure-min"]`; assert
  the spy was **not** called and `main` returned without error.
- **Top-up path:** `get_pending` returns 5 stubs; assert `run_all_agents` **was** called.
- **No-flag regression:** without `--ensure-min`, `run_all_agents` is called regardless of queue
  depth (today's behavior preserved).

## Docs

- Update the `scripts/overnight.sh` step-1 comment to note the conditional top-up.
- Update the CLAUDE.md deploy paragraph: local overnight tops up ideas only when pending <
  `IDEATE_TOPUP_MIN`; Railway cron stays the primary generator.
- Update the automation memory (`neon-queue-railway-cron-live`).

## Out of scope / follow-ups

- Optional later: apply a depth guard to the Railway cron too (it also over-generates onto the
  deep queue, but it is cost-capped and serves as the fallback generator).
- Optional later: a recency/freshness factor in `_select` ordering (today it is pure
  `viral_score DESC`). Explicitly deferred — separate selection-policy change.
