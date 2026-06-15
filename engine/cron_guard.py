"""Cost-guard math + the durable monthly-spend query for the unattended cron."""
from engine.config import DATABASE_URL


def should_skip_monthly(spent: float, cap: float) -> bool:
    return spent >= cap


def over_run_cap(run_spent: float, cap: float) -> bool:
    return run_spent >= cap


def monthly_spent_usd() -> float:
    """Sum of api_costs over the trailing 30 days (Neon). 0.0 if no DB."""
    if not DATABASE_URL:
        return 0.0
    from engine.queue import neon_backend
    with neon_backend._conn() as c:
        row = c.execute(
            "SELECT COALESCE(sum(usd), 0) FROM api_costs "
            "WHERE ts > now() - interval '30 days'").fetchone()
    return float(row[0])
