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


def summarize_neon(rows):
    """Aggregate Neon api_costs rows. rows: iterable of (agent, usd). Pure (no DB)."""
    total = 0.0
    by_stage = {}
    for agent, usd in rows:
        usd = float(usd)
        total += usd
        by_stage[agent] = by_stage.get(agent, 0.0) + usd
    return {
        "total": round(total, 4),
        "by_stage": {k: round(v, 4) for k, v in
                     sorted(by_stage.items(), key=lambda kv: -kv[1])},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Summarize API cost for an automation run.")
    p.add_argument("--run", default=None,
                   help="run_id to summarize (default: $TUG_RUN_ID or today's adhoc id)")
    p.add_argument("--neon", action="store_true",
                   help="summarize the durable Neon api_costs ledger (includes the Railway cron)")
    args = p.parse_args(argv)
    if args.neon:
        if not config.DATABASE_URL:
            print("--neon requires DATABASE_URL to be set")
            return 1
        from engine.queue import neon_backend
        with neon_backend._conn() as c:
            rows = c.execute("SELECT agent, usd FROM api_costs").fetchall()
            trailing30 = c.execute(
                "SELECT COALESCE(sum(usd), 0) FROM api_costs "
                "WHERE ts > now() - interval '30 days'").fetchone()[0]
        agg = summarize_neon(rows)
        print(f"Neon api_costs — total ${agg['total']:.2f} | "
              f"trailing-30-day ${float(trailing30):.2f}")
        for stage, usd in agg["by_stage"].items():
            print(f"  {stage:24} ${usd:.4f}")
        return 0
    run_id = (args.run or os.environ.get("TUG_RUN_ID")
              or ("adhoc-" + datetime.date.today().isoformat()))
    agg = summarize(_rows(config.COST_LEDGER_PATH), run_id)
    print(render(agg, run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
