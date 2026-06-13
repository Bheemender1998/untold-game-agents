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


import re as _re

_TEMPORAL = _re.compile(
    r"\b(currently|right now|this (year|season|week|month)|as of|last (year|season|week|month)|"
    r"recently|nowadays|these days)\b", _re.I)
_YEAR = _re.compile(r"\b(\d{4})\b")


def _force_recent(text: str) -> bool:
    """Heuristic backstop: True if the claim looks current/recent (year >= this year, or a
    temporal phrase). Can only escalate caution, never reduce it."""
    if _TEMPORAL.search(text):
        return True
    this_year = datetime.date.today().year
    return any(int(y) >= this_year for y in _YEAR.findall(text))


# ── Extract & classify (LLM call #1) ─────────────────────────────────────────

_EXTRACT_SYSTEM = """You extract CHECKABLE factual claims from a documentary script for
fact-checking, and classify each. A checkable claim is a falsifiable assertion: a date,
score, name, quantity, sequence, or location. DROP opinion, framing, atmosphere,
rhetorical questions, and narration flourish entirely -- they are not claims.

For each checkable claim return:
- text:   the claim as a standalone sentence (resolve pronouns).
- entity: the subject to look up (the event/person/match), NOT the whole sentence.
- fact:   the specific assertion to confirm (the number/name/date/sequence).
- era:    "encyclopedic" if it is settled history; "recent" if it concerns a current or
          near-future event, an ongoing/active tally, or anything not yet encyclopedic."""

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"}, "entity": {"type": "string"},
            "fact": {"type": "string"},
            "era": {"type": "string", "enum": ["encyclopedic", "recent"]},
        },
        "required": ["text", "entity", "fact", "era"],
        "additionalProperties": False,
    }}},
    "required": ["claims"],
    "additionalProperties": False,
}


_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "he", "she",
         "it", "his", "her", "was", "were", "is", "are", "by", "for", "with", "that"}


def _keywords(fact: str) -> set[str]:
    return {w for w in _re.findall(r"[\w']+", fact.lower()) if w not in _STOP and len(w) > 3} \
        | set(_re.findall(r"\d+", fact))   # always keep bare numbers (84, 211, 1994)


def _window(extract_text: str, fact: str, max_chars: int = 1200) -> str:
    """Return the sentences of `extract_text` that contain `fact` keywords, capped to
    `max_chars`. Empty string if none match (caller treats as thin evidence)."""
    kws = _keywords(fact)
    if not kws:
        return ""
    sentences = _re.split(r"(?<=[.!?])\s+", extract_text)
    hits = [s for s in sentences if kws & _keywords(s)]
    if not hits:
        return ""
    out = " ".join(hits)
    return out[:max_chars]


# ── Extract & classify (LLM call #1) ─────────────────────────────────────────

def _resolve_title(query: str, cache: dict) -> str | None:
    res = cache["resolutions"]
    if query not in res:
        res[query] = wikipedia.search_title(query) or ""
    return res[query] or None


def _get_extract(title: str, cache: dict) -> str:
    ex = cache["extracts"]
    entry = ex.get(title)
    if entry and _fresh(entry):
        return entry["text"]
    text = wikipedia.extract(title)
    ex[title] = {"text": text, "fetched_at": time.time()}
    return text


def _mediawiki_evidence(claim: dict, cache: dict) -> dict:
    title = _resolve_title(f"{claim['entity']} {claim['fact']}", cache)
    if not title:
        return {"kind": "none", "text": "", "source": ""}
    window = _window(_get_extract(title, cache), claim["fact"])
    if not window:
        return {"kind": "none", "text": "", "source": ""}
    return {"kind": "encyclopedic", "text": window, "source": f"Wikipedia: {title}"}


def gather_evidence(claim: dict, cache: dict) -> dict:
    """Tiered: encyclopedic -> MediaWiki (cached) first; recent or MediaWiki-thin -> DDG.
    Returns Evidence; kind='none' if nothing usable (claim cannot auto-pass)."""
    if claim["era"] == "encyclopedic":
        ev = _mediawiki_evidence(claim, cache)
        if ev["kind"] == "encyclopedic":
            return ev
    web = web_search(claim["text"], max_results=5)
    if web and not web.lstrip().startswith("["):    # "[...]" = error / no-results note
        return {"kind": "web", "text": web, "source": "duckduckgo"}
    return {"kind": "none", "text": "", "source": ""}


# ── Extract & classify (LLM call #1) ─────────────────────────────────────────

def extract_and_classify(script_md: str, max_claims: int = 25) -> list[dict]:
    out = _structured(
        _EXTRACT_SYSTEM,
        f"Extract up to {max_claims} checkable claims from this script:\n\n{script_md}",
        _EXTRACT_SCHEMA)
    claims = out["claims"][:max_claims]
    for c in claims:                         # heuristic backstop can only escalate caution
        if _force_recent(c["text"]):
            c["era"] = "recent"
    return claims


# ── Judge (LLM call #2) ───────────────────────────────────────────────────────

_JUDGE_SYSTEM = """You are a rigorous fact-checker judging a batch of claims, each with its
gathered evidence. For EACH claim, judge ONLY from its evidence:
- supported   : the evidence confirms the SAME entity AND the SAME specific fact. Confidence
                floor -- only mark supported on a genuine match, never on fuzzy keyword overlap.
- contradicted: the evidence says something different -- give the CORRECTED fact.
- unverified  : the evidence is ambiguous, partial, wrong-entity, or empty. When in doubt,
                unverified -- a false 'supported' ships an error.
Source weighting: ENCYCLOPEDIC evidence outranks WEB snippets; never let a weak web snippet
override an encyclopedic confirmation. Return one verdict per claim, echoing its index."""

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "verdict": {"type": "string", "enum": ["supported", "contradicted", "unverified"]},
            "correction": {"type": "string"}, "source": {"type": "string"},
        },
        "required": ["index", "verdict", "correction", "source"],
        "additionalProperties": False,
    }}},
    "required": ["verdicts"],
    "additionalProperties": False,
}

_JUDGE_CHUNK = 20  # claims per judge call; overflow → +1 call each (rare after windowing)


def _judge_chunk(items: list[tuple]) -> list[dict]:
    """One judge call for up to _JUDGE_CHUNK (claim, evidence) items. Fails CLOSED:
    on any error every claim in the chunk becomes unverified."""
    blocks = []
    for i, (claim, ev) in enumerate(items):
        blocks.append(f"[{i}] CLAIM: {claim['text']}\n    EVIDENCE ({ev['kind']}): "
                      f"{ev['text'] or '(none)'}")
    prompt = "Judge each claim from its evidence:\n\n" + "\n\n".join(blocks)
    try:
        out = _structured(_JUDGE_SYSTEM, prompt, _JUDGE_SCHEMA, max_tokens=4096)
        by_index = {v["index"]: v for v in out["verdicts"]}
    except Exception:                              # fail closed, loudly
        by_index = {}
    verdicts = []
    for i, (claim, ev) in enumerate(items):
        v = by_index.get(i)
        verdicts.append({
            "claim": claim["text"],
            "verdict": v["verdict"] if v else "unverified",   # legacy key (not 'status')
            "correction": (v.get("correction", "") if v else ""),
            "source": (v.get("source", "") if v else ev["source"]),
            "evidence_kind": ev["kind"],
        })
    return verdicts


def judge(items: list[tuple]) -> list[dict]:
    """Batched judge over (claim, evidence) pairs → list[Verdict] aligned to input order.
    Splits into _JUDGE_CHUNK-sized calls (+1 LLM call per overflow chunk)."""
    out = []
    for start in range(0, len(items), _JUDGE_CHUNK):
        out.extend(_judge_chunk(items[start:start + _JUDGE_CHUNK]))
    return out


def factcheck(script_md: str, max_claims: int = 25) -> dict:
    """Run the gate. Returns the legacy schema (+ would_auto_pass for shadow telemetry):
      {checked, supported, issues[], complete, max_claims, passed, would_auto_pass}.

    Invariant: every checkable claim terminates in supported|contradicted|unverified; a
    claim with no usable evidence comes back unverified (an issue), never dropped. `complete`
    means extraction was NOT truncated; `passed` requires complete AND zero issues."""
    claims = extract_and_classify(script_md, max_claims)
    complete = len(claims) < max_claims          # hit the cap → coverage truncated

    cache = _cache_load()
    try:
        items = [(c, gather_evidence(c, cache)) for c in claims]
    finally:
        _cache_save(cache)

    verdicts = judge(items)
    issues = [v for v in verdicts if v["verdict"] != "supported"]  # contradicted + unverified
    supported = sum(1 for v in verdicts if v["verdict"] == "supported")
    passed = (not issues) and complete
    return {
        "checked": len(claims), "supported": supported, "issues": issues,
        "complete": complete, "max_claims": max_claims,
        "passed": passed, "would_auto_pass": passed,
    }
