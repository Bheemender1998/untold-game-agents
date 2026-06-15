"""Cost-guard math + the durable monthly-spend query for the unattended cron."""
from engine.config import DATABASE_URL


def should_skip_monthly(spent: float, cap: float) -> bool:
    return spent >= cap


def over_run_cap(run_spent: float, cap: float) -> bool:
    return run_spent >= cap


def monthly_spent_usd() -> float:
    """Sum of api_costs over a rolling, trailing 30-day window (Neon). 0.0 if no DB.

    Intentionally a rolling 30 days, NOT a calendar month (date_trunc('month')):
    a rolling window is the stricter guard for an unattended cron — a calendar
    month would reset the budget to $0 on the 1st, allowing a fresh full spend
    immediately after a late-month spike. The "monthly" cap is the ~30-day knob.
    """
    if not DATABASE_URL:
        return 0.0
    from engine.queue import neon_backend
    with neon_backend._conn() as c:
        row = c.execute(
            "SELECT COALESCE(sum(usd), 0) FROM api_costs "
            "WHERE ts > now() - interval '30 days'").fetchone()
    return float(row[0])
