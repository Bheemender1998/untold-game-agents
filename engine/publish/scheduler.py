"""Pick a publish slot from profiles/cadence.yaml."""
from __future__ import annotations
import datetime


def next_slot(after: datetime.date) -> datetime.datetime:
    """TODO (Stage 2): read cadence.yaml; return next free publish datetime."""
    return datetime.datetime.combine(after, datetime.time(16, 0))
