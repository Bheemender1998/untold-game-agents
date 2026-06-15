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
