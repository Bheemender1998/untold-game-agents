"""
Fact-verification gate (engine, 2026-06-13 redesign of ADR-0005).

Pipeline: extract_and_classify (1 LLM call, drops uncheckable) -> gather_evidence
(MediaWiki-first for encyclopedic, DDG fallback for recent/thin, cached) -> judge
(1 batched LLM call, confidence floor) -> factcheck (aggregate to the legacy schema).

Auto-correction is gone -- the gate emits verdicts only; humans fix. Ships behind
config.FACT_GATE_SHADOW. See docs/superpowers/specs/2026-06-13-fact-gate-design.md.

Data shapes:
  Claim    = {"text","entity","fact","era": "encyclopedic"|"recent"}
  Evidence = {"kind": "encyclopedic"|"web"|"none", "text", "source"}
  Verdict  = {"claim","verdict","correction","source","evidence_kind"}  # key 'verdict' (legacy)
"""
from __future__ import annotations
import datetime
import json
import os
import time

import anthropic
from engine import config
from engine.config import MODEL
from engine.ideate import wikipedia
from engine.ideate.web_search import search as web_search

_client = anthropic.Anthropic(max_retries=5)


def _structured(system: str, prompt: str, schema: dict, max_tokens: int = 4096) -> dict:
    resp = _client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


# ── Persistent entity cache ───────────────────────────────────────────────────

def _cache_load() -> dict:
    try:
        with open(config.FACTCACHE_PATH) as f:
            d = json.load(f)
        d.setdefault("resolutions", {})
        d.setdefault("extracts", {})
        return d
    except (FileNotFoundError, ValueError, OSError):
        return {"resolutions": {}, "extracts": {}}


def _cache_save(cache: dict) -> None:
    tmp = config.FACTCACHE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, config.FACTCACHE_PATH)  # atomic


def _fresh(entry: dict) -> bool:
    return (time.time() - entry.get("fetched_at", 0)) < config.FACTCACHE_TTL_DAYS * 86400
