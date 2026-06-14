"""
Aggregate the API cost ledger (logs/api-cost.jsonl) by run and print a per-stage
summary plus a budget warning if a run exceeds config.COST_ALERT_USD. Reporter
only — always exits 0; never gates a run.
See docs/superpowers/specs/2026-06-14-api-cost-tracking-design.md.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os

from engine import config


def _rows(path: str):
    """Yield parsed ledger rows; skip malformed lines; tolerate a missing file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    print("cost-report warning: skipping malformed ledger line")
    except (FileNotFoundError, OSError):
        return


def summarize(rows, run_id: str) -> dict:
    """Group this run's rows by stage -> {calls, input, output, cost}."""
    agg = collections.defaultdict(
        lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
    )
    for r in rows:
        if r.get("run_id") != run_id:
            continue
        s = agg[r.get("stage", "?")]
        s["calls"] += 1
        s["input"] += (r.get("input_tokens", 0)
                       + r.get("cache_creation_input_tokens", 0)
                       + r.get("cache_read_input_tokens", 0))
        s["output"] += r.get("output_tokens", 0)
        s["cost"] += r.get("cost_usd", 0.0)
    return dict(agg)


def render(agg: dict, run_id: str) -> str:
    header = f"── API cost — run {run_id} ──"
    if not agg:
        return header + "\n  no cost data for this run"
    lines = [header]
    total_calls = 0
    total_cost = 0.0
    for stage in sorted(agg):
        s = agg[stage]
        total_calls += s["calls"]
        total_cost += s["cost"]
        lines.append(
            f"  {stage:<16}{s['calls']:>3} calls  "
            f"{s['input'] // 1000:>5}k in {s['output'] // 1000:>5}k out  ${s['cost']:.2f}"
        )
    lines.append("  " + "─" * 51)
    lines.append(f"  {'TOTAL':<16}{total_calls:>3} calls{'':>20}${total_cost:.2f}")
    if total_cost > config.COST_ALERT_USD:
        lines.append(
            f"⚠️  BUDGET: run cost ${total_cost:.2f} "
            f"exceeds ${config.COST_ALERT_USD:.2f} cap"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Summarize API cost for an automation run.")
    p.add_argument("--run", default=None,
                   help="run_id to summarize (default: $TUG_RUN_ID or today's adhoc id)")
    args = p.parse_args(argv)
    run_id = (args.run or os.environ.get("TUG_RUN_ID")
              or ("adhoc-" + datetime.date.today().isoformat()))
    agg = summarize(_rows(config.COST_LEDGER_PATH), run_id)
    print(render(agg, run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
