"""Snapshot performance for the recently-published cohort."""
from __future__ import annotations
import datetime


def snapshot(as_of: datetime.date) -> dict:
    """TODO (Stage 3): pull views/CTR/retention for published videos; persist."""
    return {"as_of": str(as_of), "videos": []}
