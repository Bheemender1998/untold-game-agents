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

from engine.config import COST_LEDGER_PATH

# Per-token USD, from the claude-api reference (2026-06): Sonnet 4.6 is
# $3/1M input, $15/1M output; cache writes 1.25x input, cache reads 0.10x input.
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read":  0.30 / 1_000_000,
    },
}


def cost_usd(usage, model: str) -> float:
    """USD for one response's usage. Unknown model -> 0.0 (caller logs a warning)."""
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return (
        (getattr(usage, "input_tokens", 0) or 0) * rates["input"]
        + (getattr(usage, "output_tokens", 0) or 0) * rates["output"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * rates["cache_write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * rates["cache_read"]
    )
