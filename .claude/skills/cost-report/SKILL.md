---
name: cost-report
description: Summarize TUG API spend from the cost ledger and triage budget alerts. Use when the user says "cost report", "how much did the run cost", "check API spend", "$10 alert", or "/cost-report".
---

# API cost report / triage

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.

- **All runs in the ledger:** `python3 -m engine.run_cost_report`
- **One run by id:** `python3 -m engine.run_cost_report --run <TUG_RUN_ID>`

How it works: every `messages.create` is priced and appended to `logs/api-cost.jsonl`
(via `engine/usage.py`). The report groups by `run_id`, prints a per-stage breakdown,
and warns when a run exceeds `config.COST_ALERT_USD` ($10). It is **reporter-only** —
always exits 0, never gates a run. `overnight.sh` runs it automatically per run and
folds the summary into the daily log.

Triage: a typical 3-video run is ≈ $0.42; a ~20-script runaway trips the $10 alert. If a
run is unexpectedly high, read the per-stage breakdown (script / metadata / fact-gate /
thumbnail) — the runaway pattern is repeated produce loops re-spending on scripts.
