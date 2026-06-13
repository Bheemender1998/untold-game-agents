"""Thin shim — the fact-gate engine moved to engine.pipeline.fact_gate (2026-06-13
redesign of ADR-0005). Kept so existing imports keep working; the factcheck.json schema
is unchanged. Auto-correction was REMOVED (human-only): there is no correct_script.

See docs/superpowers/specs/2026-06-13-fact-gate-design.md."""
from __future__ import annotations

from engine.pipeline.fact_gate import factcheck, extract_and_classify  # noqa: F401 (re-export)
