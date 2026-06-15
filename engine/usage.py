"""
API cost tracking — prices each Anthropic response and appends to a JSONL ledger.

Wrap every messages.create call site in logged_create(...) so resp.usage is
captured. Recording is best-effort and never raises (self-stub rule): a cost-
tracking failure must never crash a production run.
See docs/superpowers/specs/2026-06-14-api-cost-tracking-design.md.
"""
from __future__ import annotations

import datetime
import json
import os
import re

from engine.config import COST_LEDGER_PATH

# The API echoes a resolved, dated model id (e.g. "claude-haiku-4-5-20251001") while PRICING
# is keyed on the alias ("claude-haiku-4-5"). Strip a trailing -YYYYMMDD before the lookup so
# dated ids price correctly instead of logging $0 (bug #58).
_DATE_SUFFIX = re.compile(r"-\d{8}$")


def _pricing_key(model: str) -> str:
    """Normalize a returned model id to its PRICING alias by dropping a -YYYYMMDD suffix."""
    return _DATE_SUFFIX.sub("", model or "")

# Per-token USD, from the claude-api reference (2026-06): Sonnet 4.6 is
# $3/1M input, $15/1M output; cache writes 1.25x input, cache reads 0.10x input.
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read":  0.30 / 1_000_000,
    },
    "claude-haiku-4-5": {
        "input":       1.00 / 1_000_000,
        "output":      5.00 / 1_000_000,
        "cache_write": 1.25 / 1_000_000,
        "cache_read":  0.10 / 1_000_000,
    },
}


def cost_usd(usage, model: str) -> float:
    """USD for one response's usage. Unknown model -> 0.0 (caller logs a warning)."""
    rates = PRICING.get(_pricing_key(model))
    if rates is None:
        return 0.0
    return (
        (getattr(usage, "input_tokens", 0) or 0) * rates["input"]
        + (getattr(usage, "output_tokens", 0) or 0) * rates["output"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * rates["cache_write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * rates["cache_read"]
    )


def _run_id() -> str:
    return os.environ.get("TUG_RUN_ID") or ("adhoc-" + datetime.date.today().isoformat())


def record(resp, stage: str) -> None:
    """Append one priced ledger row for a response. Best-effort; never raises."""
    try:
        u = resp.usage
        model = getattr(resp, "model", "") or ""
        if _pricing_key(model) not in PRICING:
            print(f"cost-track warning: unknown model {model!r}; logged $0")
        row = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "run_id": _run_id(),
            "stage": stage,
            "model": model,
            "input_tokens": getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cost_usd": round(cost_usd(u, model), 6),
        }
        # Harden against a fresh checkout / a caller with a different CWD: a
        # missing logs/ dir would otherwise drop the whole run's telemetry.
        os.makedirs(os.path.dirname(COST_LEDGER_PATH) or ".", exist_ok=True)
        # Single small append in "a" (O_APPEND) mode — atomic per write() at the
        # OS level, so the overnight run's parallel ideation threads don't
        # interleave rows (each row is well under PIPE_BUF).
        with open(COST_LEDGER_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:  # cost tracking must never crash a run
        print(f"cost-track warning: {e}")
    # Durable ledger for the unattended cron's monthly cap (Railway fs is ephemeral).
    try:
        from engine.config import DATABASE_URL
        if DATABASE_URL:
            from engine.queue import neon_backend
            with neon_backend._conn() as c:
                c.execute(
                    "INSERT INTO api_costs (agent, run_id, usd) VALUES (%s,%s,%s)",
                    (stage, _run_id(), cost_usd(u, model)))
    except Exception as e:                       # never crash a production run
        print(f"cost-track warning: neon ledger write failed: {e}")


def logged_create(client, stage: str, **kwargs):
    """client.messages.create(**kwargs) with usage recorded to the ledger.

    The API call itself is NOT wrapped — real API errors propagate unchanged.
    Only the recording is best-effort.
    """
    resp = client.messages.create(**kwargs)
    record(resp, stage)
    return resp
